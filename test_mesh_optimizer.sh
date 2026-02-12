#!/bin/bash
# Test script for mesh_optimizer with before/after comparison
# Usage: ./test_mesh_optimizer.sh [path_to_stl]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

# Activate venv
if [[ ! -f "${VENV_DIR}/bin/activate" ]]; then
    echo "ERROR: Virtual environment not found. Run: python3 -m venv .venv && source .venv/bin/activate && pip install numpy trimesh"
    exit 1
fi

source "${VENV_DIR}/bin/activate"

# Get input file
INPUT_FILE="${1:-}"
if [[ -z "${INPUT_FILE}" ]]; then
    echo "Usage: $0 <path_to_stl_file>"
    echo ""
    echo "Example: $0 /path/to/benchy.stl"
    echo ""
    echo "Available samples:"
    ls -lhS samples/*.stl | awk '{print "  " $9 " (" $5 ")"}'
    exit 1
fi

if [[ ! -f "${INPUT_FILE}" ]]; then
    echo "ERROR: File not found: ${INPUT_FILE}"
    exit 1
fi

# Get file size
INPUT_SIZE=$(stat -f%z "${INPUT_FILE}" 2>/dev/null || stat -c%s "${INPUT_FILE}" 2>/dev/null)
INPUT_SIZE_MB=$(echo "scale=2; ${INPUT_SIZE} / 1048576" | bc)

echo "============================================"
echo "MESH OPTIMIZER TEST"
echo "============================================"
echo ""
echo "Input File: ${INPUT_FILE}"
echo "File Size:  ${INPUT_SIZE_MB} MB"
echo ""

# Stage 1: Analyze original
echo "[Stage 1] ANALYZING ORIGINAL MESH"
echo "--------------------------------------------"
ORIGINAL_ANALYSIS=$(mktemp)
python3 -m pycam.Utils.mesh_optimizer detect "${INPUT_FILE}" | tee "${ORIGINAL_ANALYSIS}"
echo ""

# Extract metrics
ORIGINAL_TRIANGLES=$(grep "triangle_count" "${ORIGINAL_ANALYSIS}" | awk '{print $NF}')
ORIGINAL_DENSITY=$(grep "density_triangles_per_mm3" "${ORIGINAL_ANALYSIS}" | awk '{print $NF}')
ORIGINAL_VOLUME=$(grep "volume" "${ORIGINAL_ANALYSIS}" | awk '{print $NF}')
ORIGINAL_SA=$(grep "surface_area" "${ORIGINAL_ANALYSIS}" | awk '{print $NF}')

echo "Summary (Original):"
echo "  Triangles:    ${ORIGINAL_TRIANGLES}"
echo "  Density:      ${ORIGINAL_DENSITY} tri/mm³"
echo "  Volume:       ${ORIGINAL_VOLUME} mm³"
echo "  Surface Area: ${ORIGINAL_SA} mm²"
echo ""

# Stage 2: Adaptive reduction
echo "[Stage 2] ADAPTIVE REDUCTION ANALYSIS"
echo "--------------------------------------------"
REDUCED_FILE="${INPUT_FILE%.*}_reduced_auto.stl"
REDUCTION_ANALYSIS=$(mktemp)
python3 -m pycam.Utils.mesh_optimizer reduce-auto "${INPUT_FILE}" 2>&1 | tee "${REDUCTION_ANALYSIS}"
echo ""

# Extract reduction metrics
if grep -q "was_reduced" "${REDUCTION_ANALYSIS}"; then
    REDUCED_TRIANGLES=$(grep "reduced_count" "${REDUCTION_ANALYSIS}" | awk '{print $NF}')
    REDUCTION_PCT=$(grep "reduction_percentage" "${REDUCTION_ANALYSIS}" | awk '{print $NF}')
    NEW_DENSITY=$(grep "new_density" "${REDUCTION_ANALYSIS}" | awk '{print $NF}')
    STRATEGY=$(grep "strategy" "${REDUCTION_ANALYSIS}" | grep -v "Using strategy" | awk -F': ' '{print $NF}')
    
    REDUCED_FILE=$(ls -t "${INPUT_FILE%/*}"/*_reduced_auto.stl 2>/dev/null | head -1)
    if [[ -f "${REDUCED_FILE}" ]]; then
        REDUCED_SIZE=$(stat -f%z "${REDUCED_FILE}" 2>/dev/null || stat -c%s "${REDUCED_FILE}" 2>/dev/null)
        REDUCED_SIZE_MB=$(echo "scale=2; ${REDUCED_SIZE} / 1048576" | bc)
        
        echo "Summary (Reduced):"
        echo "  Reduced File: ${REDUCED_FILE}"
        echo "  File Size:    ${REDUCED_SIZE_MB} MB (was ${INPUT_SIZE_MB} MB)"
        echo "  Triangles:    ${REDUCED_TRIANGLES} (was ${ORIGINAL_TRIANGLES})"
        echo "  Reduction:    ${REDUCTION_PCT}%"
        echo "  New Density:  ${NEW_DENSITY} tri/mm³ (was ${ORIGINAL_DENSITY})"
        echo "  Strategy:     ${STRATEGY}"
    fi
else
    echo "Mesh already at low density. No reduction needed."
fi

echo ""
echo "============================================"
echo "ANALYSIS COMPLETE"
echo "============================================"
echo ""

# Cleanup
rm -f "${ORIGINAL_ANALYSIS}" "${REDUCTION_ANALYSIS}"
