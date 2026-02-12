#!/usr/bin/env python3
"""
Mesh density detection and reduction utilities.

Supports:
1. Mesh Density Analysis: Triangle count, density metrics, aspect ratios
2. Mesh Reduction: Quadric Error Metric (QEM) decimation algorithm
"""

import numpy as np
from pathlib import Path
from typing import Tuple, Dict, Optional

import pycam.Utils.log

try:
    import trimesh
except ImportError:
    trimesh = None

log = pycam.Utils.log.get_logger()


class MeshDensityAnalyzer:
    """Detect and analyze mesh density characteristics."""

    @staticmethod
    def detect_mesh_density(mesh_path: str) -> Dict[str, float]:
        """
        Analyze mesh density and return multiple metrics.

        Args:
            mesh_path: Path to STL file

        Returns:
            Dictionary with keys:
            - triangle_count: Total number of triangles
            - density_triangles_per_mm3: Triangles per cubic millimeter
            - avg_edge_length: Average edge length in mm
            - aspect_ratio: Average triangle aspect ratio (1.0 = equilateral)
            - volume: Mesh volume in mm³
            - surface_area: Mesh surface area in mm²
            - is_high_density: Boolean, True if density > 10 triangles/mm³
        """
        if trimesh is None:
            raise ImportError("trimesh library required. Install: pip install trimesh numpy-stl")

        try:
            mesh = trimesh.load_mesh(mesh_path)
        except Exception as e:
            log.error(f"Failed to load mesh: {e}")
            raise

        triangle_count = len(mesh.faces)
        volume = mesh.volume
        surface_area = mesh.area

        # Edge lengths
        edges = mesh.edges_unique
        edge_vectors = mesh.vertices[edges[:, 1]] - mesh.vertices[edges[:, 0]]
        edge_lengths = np.linalg.norm(edge_vectors, axis=1)
        avg_edge_length = np.mean(edge_lengths)

        # Aspect ratio: ratio of longest to shortest edge per triangle
        aspect_ratios = []
        for face in mesh.faces:
            vertices = mesh.vertices[face]
            edge1 = np.linalg.norm(vertices[1] - vertices[0])
            edge2 = np.linalg.norm(vertices[2] - vertices[1])
            edge3 = np.linalg.norm(vertices[0] - vertices[2])
            edges_tri = sorted([edge1, edge2, edge3])
            if edges_tri[0] > 0:
                aspect_ratio = edges_tri[2] / edges_tri[0]
                aspect_ratios.append(aspect_ratio)

        avg_aspect_ratio = np.mean(aspect_ratios) if aspect_ratios else 1.0

        # Density metric: triangles per unit volume
        density = triangle_count / volume if volume > 0 else 0

        return {
            "triangle_count": int(triangle_count),
            "density_triangles_per_mm3": round(density, 4),
            "avg_edge_length": round(float(avg_edge_length), 4),
            "aspect_ratio": round(float(avg_aspect_ratio), 4),
            "volume": round(float(volume), 2),
            "surface_area": round(float(surface_area), 2),
            "is_high_density": density > 10.0,
        }

    @staticmethod
    def get_density_assessment(density_metrics: Dict) -> str:
        """
        Return human-readable density assessment.

        Args:
            density_metrics: Output from detect_mesh_density()

        Returns:
            String description of mesh density
        """
        density = density_metrics["density_triangles_per_mm3"]
        tri_count = density_metrics["triangle_count"]

        if density > 50:
            return f"VERY HIGH DENSITY ({tri_count} triangles, {density} tri/mm³) - Consider reduction"
        elif density > 20:
            return f"HIGH DENSITY ({tri_count} triangles, {density} tri/mm³)"
        elif density > 10:
            return f"MODERATE-HIGH DENSITY ({tri_count} triangles, {density} tri/mm³)"
        elif density > 5:
            return f"MODERATE DENSITY ({tri_count} triangles, {density} tri/mm³)"
        else:
            return f"LOW DENSITY ({tri_count} triangles, {density} tri/mm³)"


class MeshDensityReducer:
    """Reduce mesh density using proven decimation algorithms."""

    @staticmethod
    def reduce_mesh_density_qem(
        mesh_path: str,
        target_count: Optional[int] = None,
        target_ratio: float = 0.5,
        output_path: Optional[str] = None,
        aggressiveness: float = 7.0,
        max_iterations: int = 100,
    ) -> str:
        """
        Reduce mesh density using Quadric Error Metric (QEM) decimation.

        This is the industry-standard algorithm used by MeshLab, Blender, and
        professional CAD tools. It preserves mesh features while reducing triangles.

        Args:
            mesh_path: Path to input STL file
            target_count: Target triangle count (if None, use target_ratio)
            target_ratio: Target as ratio of original (e.g., 0.5 = 50% reduction)
            output_path: Output STL path (default: input_path_reduced.stl)
            aggressiveness: Higher = more aggressive reduction (recommended: 5-10)
            max_iterations: Maximum decimation iterations

        Returns:
            Path to reduced mesh file

        Example:
            >>> input_file = "high_density.stl"
            >>> output = MeshDensityReducer.reduce_mesh_density_qem(
            ...     input_file,
            ...     target_ratio=0.50,  # Keep 50% of triangles
            ...     aggressiveness=7.0
            ... )
            >>> print(f"Reduced mesh saved to: {output}")
        """
        if trimesh is None:
            raise ImportError("trimesh library required. Install: pip install trimesh")

        try:
            mesh = trimesh.load_mesh(mesh_path)
        except Exception as e:
            log.error(f"Failed to load mesh: {e}")
            raise

        original_count = len(mesh.faces)
        log.info(f"Original mesh: {original_count} triangles")

        # Determine target count
        if target_count is None:
            target_count = max(4, int(original_count * target_ratio))

        if target_count >= original_count:
            log.warning("Target count >= original count. Skipping reduction.")
            return mesh_path

        reduction_ratio = 1.0 - (target_count / original_count)

        try:
            # trimesh.simplify uses quadric error metric internally
            mesh_simplified = mesh.simplify_quadratic_mesh(
                target_reduction=reduction_ratio,
                aggressiveness=aggressiveness,
                max_iterations=max_iterations,
                preserve_border=True,
            )
        except AttributeError:
            # Fallback for older trimesh versions
            log.info("Using alternative simplification method...")
            mesh_simplified = mesh.simplify_quadratic_mesh(
                target_count=target_count
            )

        new_count = len(mesh_simplified.faces)
        log.info(
            f"Simplified mesh: {new_count} triangles "
            f"({new_count / original_count * 100:.1f}% of original)"
        )

        # Default output path
        if output_path is None:
            input_path = Path(mesh_path)
            output_path = str(input_path.parent / f"{input_path.stem}_reduced.stl")

        # Export
        try:
            mesh_simplified.export(output_path)
            log.info(f"Simplified mesh exported to: {output_path}")
        except Exception as e:
            log.error(f"Failed to export mesh: {e}")
            raise

        return output_path

    @staticmethod
    def reduce_mesh_density_voxel(
        mesh_path: str,
        voxel_size: float = 1.0,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Reduce mesh density using voxel/grid-based simplification.

        Fast alternative to QEM. Merges vertices within voxel cells.
        Good for highly detailed scanned models.

        Args:
            mesh_path: Path to input STL file
            voxel_size: Size of voxel grid in mm (larger = more reduction)
            output_path: Output STL path (default: input_path_voxel.stl)

        Returns:
            Path to reduced mesh file

        Example:
            >>> output = MeshDensityReducer.reduce_mesh_density_voxel(
            ...     "detailed_scan.stl",
            ...     voxel_size=2.0  # 2mm voxel grid
            ... )
        """
        if trimesh is None:
            raise ImportError("trimesh library required. Install: pip install trimesh")

        try:
            mesh = trimesh.load_mesh(mesh_path)
        except Exception as e:
            log.error(f"Failed to load mesh: {e}")
            raise

        original_count = len(mesh.faces)
        log.info(f"Original mesh: {original_count} triangles")

        try:
            # Voxelization and re-meshing
            voxels = mesh.voxelized(voxel_size)
            mesh_simplified = voxels.as_mesh()
        except Exception as e:
            log.error(f"Voxelization failed: {e}")
            raise

        new_count = len(mesh_simplified.faces)
        log.info(
            f"Voxelized mesh: {new_count} triangles "
            f"({new_count / original_count * 100:.1f}% of original)"
        )

        # Default output path
        if output_path is None:
            input_path = Path(mesh_path)
            output_path = str(input_path.parent / f"{input_path.stem}_voxel.stl")

        try:
            mesh_simplified.export(output_path)
            log.info(f"Voxelized mesh exported to: {output_path}")
        except Exception as e:
            log.error(f"Failed to export mesh: {e}")
            raise

        return output_path

    @staticmethod
    def adaptive_reduce(
        mesh_path: str,
        output_path: Optional[str] = None,
        auto_detect: bool = True,
    ) -> Tuple[str, Dict]:
        """
        Automatically reduce mesh density based on analysis.

        Detects density and applies appropriate reduction strategy:
        - density > 50 tri/mm³: Aggressive QEM (70% reduction)
        - density > 20 tri/mm³: Moderate QEM (50% reduction)
        - density > 10 tri/mm³: Light QEM (30% reduction)
        - density <= 10 tri/mm³: No reduction

        Args:
            mesh_path: Path to input STL file
            output_path: Optional output path
            auto_detect: If True, run density analysis before reduction

        Returns:
            Tuple of (output_path, reduction_metrics)

        Example:
            >>> reduced_path, metrics = MeshDensityReducer.adaptive_reduce(
            ...     mesh_path="unknown_density.stl"
            ... )
            >>> if metrics['was_reduced']:
            ...     print(f"Reduction: {metrics['reduction_percentage']:.1f}%")
        """
        analyzer = MeshDensityAnalyzer()
        reducer = MeshDensityReducer()

        # Analyze density
        metrics = analyzer.detect_mesh_density(mesh_path)
        density = metrics["density_triangles_per_mm3"]

        reduction_metrics = {
            "was_reduced": False,
            "original_count": metrics["triangle_count"],
            "density": density,
            "assessment": analyzer.get_density_assessment(metrics),
        }

        # Skip reduction for low-density meshes
        if density <= 10:
            log.info(f"Mesh density is low ({density} tri/mm³). No reduction needed.")
            reduction_metrics["reason"] = "Low density"
            return mesh_path, reduction_metrics

        # Apply strategy based on density
        if density > 50:
            target_ratio = 0.30  # 70% reduction
            strategy = "Aggressive QEM (70% reduction)"
        elif density > 20:
            target_ratio = 0.50  # 50% reduction
            strategy = "Moderate QEM (50% reduction)"
        else:  # 10 < density <= 20
            target_ratio = 0.70  # 30% reduction
            strategy = "Light QEM (30% reduction)"

        log.info(f"Using strategy: {strategy}")

        try:
            reduced_path = reducer.reduce_mesh_density_qem(
                mesh_path,
                target_ratio=target_ratio,
                output_path=output_path,
            )

            # Analyze reduced mesh
            reduced_metrics = analyzer.detect_mesh_density(reduced_path)
            reduction_metrics["was_reduced"] = True
            reduction_metrics["reduced_count"] = reduced_metrics["triangle_count"]
            reduction_metrics["reduction_percentage"] = (
                (metrics["triangle_count"] - reduced_metrics["triangle_count"])
                / metrics["triangle_count"]
                * 100
            )
            reduction_metrics["new_density"] = reduced_metrics[
                "density_triangles_per_mm3"
            ]
            reduction_metrics["strategy"] = strategy

            return reduced_path, reduction_metrics

        except Exception as e:
            log.error(f"Adaptive reduction failed: {e}")
            reduction_metrics["error"] = str(e)
            return mesh_path, reduction_metrics


# CLI Usage Example
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    if len(sys.argv) < 2:
        print("Usage:")
        print("  Detect density:    python mesh_optimizer.py detect <mesh.stl>")
        print("  Reduce (QEM):      python mesh_optimizer.py reduce-qem <mesh.stl> [target_ratio]")
        print("  Reduce (voxel):    python mesh_optimizer.py reduce-voxel <mesh.stl> [voxel_size]")
        print("  Adaptive reduce:   python mesh_optimizer.py reduce-auto <mesh.stl>")
        sys.exit(1)

    command = sys.argv[1]
    mesh_path = sys.argv[2]

    analyzer = MeshDensityAnalyzer()
    reducer = MeshDensityReducer()

    if command == "detect":
        metrics = analyzer.detect_mesh_density(mesh_path)
        print("\nMesh Density Analysis:")
        print("=" * 50)
        for key, value in metrics.items():
            print(f"  {key:.<35} {value}")
        print(f"\n  Assessment: {analyzer.get_density_assessment(metrics)}")

    elif command == "reduce-qem":
        target_ratio = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
        output = reducer.reduce_mesh_density_qem(mesh_path, target_ratio=target_ratio)
        print(f"\nReduced mesh saved to: {output}")

    elif command == "reduce-voxel":
        voxel_size = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
        output = reducer.reduce_mesh_density_voxel(mesh_path, voxel_size=voxel_size)
        print(f"\nVoxelized mesh saved to: {output}")

    elif command == "reduce-auto":
        output, metrics = reducer.adaptive_reduce(mesh_path)
        print("\nAdaptive Reduction Results:")
        print("=" * 50)
        for key, value in metrics.items():
            print(f"  {key:.<35} {value}")
        if metrics["was_reduced"]:
            print(f"\n  Output: {output}")
