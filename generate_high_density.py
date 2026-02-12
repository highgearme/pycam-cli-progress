#!/usr/bin/env python3
"""
Generate high-density test STL by subdividing faces.
Useful for testing mesh_optimizer without a pre-existing high-density file.
"""

import struct
import sys
from pathlib import Path


def read_binary_stl(filepath):
    """Read binary STL file."""
    with open(filepath, 'rb') as f:
        header = f.read(80)
        count_bytes = f.read(4)
        count = struct.unpack('<I', count_bytes)[0]
        
        triangles = []
        for _ in range(count):
            data = f.read(50)
            if len(data) < 50:
                break
            normal = struct.unpack('<3f', data[0:12])
            v1 = struct.unpack('<3f', data[12:24])
            v2 = struct.unpack('<3f', data[24:36])
            v3 = struct.unpack('<3f', data[36:48])
            triangles.append((normal, v1, v2, v3))
    
    return triangles


def write_binary_stl(filepath, triangles):
    """Write binary STL file."""
    with open(filepath, 'wb') as f:
        header = b"Generated high-density test mesh".ljust(80, b'\0')
        f.write(header)
        f.write(struct.pack('<I', len(triangles)))
        
        for normal, v1, v2, v3 in triangles:
            f.write(struct.pack('<3f', *normal))
            f.write(struct.pack('<3f', *v1))
            f.write(struct.pack('<3f', *v2))
            f.write(struct.pack('<3f', *v3))
            f.write(struct.pack('<H', 0))  # Attribute byte count


def subdivide_triangle(normal, v1, v2, v3, depth=1):
    """Recursively subdivide triangle to create higher density."""
    if depth == 0:
        return [(normal, v1, v2, v3)]
    
    # Midpoints
    mid12 = tuple((v1[i] + v2[i]) / 2 for i in range(3))
    mid23 = tuple((v2[i] + v3[i]) / 2 for i in range(3))
    mid31 = tuple((v3[i] + v1[i]) / 2 for i in range(3))
    
    # Recursively subdivide 4 triangles
    result = []
    result.extend(subdivide_triangle(normal, v1, mid12, mid31, depth - 1))
    result.extend(subdivide_triangle(normal, v2, mid23, mid12, depth - 1))
    result.extend(subdivide_triangle(normal, v3, mid31, mid23, depth - 1))
    result.extend(subdivide_triangle(normal, mid12, mid23, mid31, depth - 1))
    
    return result


def main():
    if len(sys.argv) < 3:
        print("Usage: generate_high_density.py <input.stl> <output.stl> [subdivision_depth]")
        print("")
        print("Subdivision depth (default=2):")
        print("  0 = 1x (no change)")
        print("  1 = 4x density (4 triangles per 1)")
        print("  2 = 16x density (16 triangles per 1)")
        print("  3 = 64x density (64 triangles per 1)")
        print("  4 = 256x density (256 triangles per 1)")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    depth = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    
    if not Path(input_file).exists():
        print(f"ERROR: Input file not found: {input_file}")
        sys.exit(1)
    
    print(f"Reading: {input_file}")
    triangles = read_binary_stl(input_file)
    original_count = len(triangles)
    print(f"  Original: {original_count} triangles")
    
    print(f"Subdividing with depth {depth}...")
    new_triangles = []
    for normal, v1, v2, v3 in triangles:
        new_triangles.extend(subdivide_triangle(normal, v1, v2, v3, depth))
    
    new_count = len(new_triangles)
    multiplier = new_count / original_count if original_count > 0 else 0
    
    print(f"  Result: {new_count} triangles ({multiplier:.1f}x)")
    
    print(f"Writing: {output_file}")
    write_binary_stl(output_file, new_triangles)
    
    input_size = Path(input_file).stat().st_size / (1024 * 1024)
    output_size = Path(output_file).stat().st_size / (1024 * 1024)
    
    print(f"  Input size:  {input_size:.2f} MB")
    print(f"  Output size: {output_size:.2f} MB ({output_size / input_size:.1f}x)")
    print("")
    print("High-density test file generated successfully!")


if __name__ == "__main__":
    main()
