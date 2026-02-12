#!/usr/bin/env python3
"""
Generate valid high-density test STL by creating a complex surface.
Uses trimesh to ensure proper normals and geometry.
"""

import struct
import sys
from pathlib import Path

try:
    import trimesh
    import numpy as np
except ImportError:
    print("ERROR: trimesh and numpy required. Install: pip install trimesh numpy")
    sys.exit(1)


def create_sphere_high_density(radius=10.0, subdivisions=4):
    """Create high-density sphere using triangulation."""
    # Create base icosphere
    sphere = trimesh.creation.icosphere(subdivisions=subdivisions, radius=radius)
    return sphere


def duplicate_and_offset_faces(mesh, n_copies=4, offset=0.01):
    """Duplicate mesh faces with small offsets to increase density without changing geometry."""
    vertices = mesh.vertices.copy()
    faces = mesh.faces.copy()
    
    # Create offset copies
    all_vertices = [vertices]
    all_faces = [faces]
    
    for i in range(1, n_copies):
        offset_vertices = vertices + np.random.normal(0, offset, vertices.shape)
        all_vertices.append(offset_vertices)
        
        # Offset face indices
        offset_faces = faces + (len(vertices) * i)
        all_faces.append(offset_faces)
    
    # Combine
    combined_vertices = np.vstack(all_vertices)
    combined_faces = np.vstack(all_faces)
    
    return trimesh.Trimesh(vertices=combined_vertices, faces=combined_faces)


def main():
    if len(sys.argv) < 2:
        print("Usage: create_dense_sphere.py <output.stl> [subdivisions] [density_multiplier]")
        print("")
        print("Parameters (defaults):")
        print("  subdivisions: 4-6 (higher = more complex)")
        print("  density_multiplier: 1-4 (how many copies to overlay)")
        print("")
        print("Examples:")
        print("  create_dense_sphere.py /tmp/dense_simple.stl 4 2    # ~3000 triangles, 3 MB")
        print("  create_dense_sphere.py /tmp/dense_medium.stl 5 3    # ~20000 triangles, 10 MB")
        sys.exit(1)
    
    output_file = sys.argv[1]
    subdivisions = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    density_mult = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    
    print(f"Creating high-density sphere...")
    print(f"  Subdivisions: {subdivisions}")
    print(f"  Density multiplier: {density_mult}")
   
    # Create base mesh
    sphere = create_sphere_high_density(radius=10.0, subdivisions=subdivisions)
    original_count = len(sphere.faces)
    print(f"  Base sphere: {original_count} triangles")
    
    # Add density
    if density_mult > 1:
        print(f"  Adding density...")
        sphere = duplicate_and_offset_faces(sphere, n_copies=density_mult, offset=0.02)
    
    final_count = len(sphere.faces)
    multiplier = final_count / original_count if original_count > 0 else 0
    
    print(f"  Final: {final_count} triangles ({multiplier:.1f}x)")
    
    # Export
    print(f"Writing: {output_file}")
    sphere.export(output_file)
    
    file_size = Path(output_file).stat().st_size / (1024 * 1024)
    print(f"  File size: {file_size:.2f} MB")
    print("")
    print("Dense sphere generated successfully!")


if __name__ == "__main__":
    main()
