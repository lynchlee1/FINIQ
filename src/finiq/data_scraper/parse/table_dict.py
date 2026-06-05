"""Generic table parser converting HTML tables to list of dictionaries."""

from __future__ import annotations

from typing import Any
from bs4 import Tag
from ._markup import _clean_text

def parse_table_to_dicts(table_tag: Tag) -> list[dict[str, str]]:
    """HTML 테이블을 2차원 배열로 풀고(Unroll), 첫 행을 Key로 하여 딕셔너리 리스트로 변환한다.
    
    colspan과 rowspan을 반영하여 빈 칸을 원래 셀의 텍스트로 채운다(Fill).
    """
    rows = table_tag.find_all("tr")
    if not rows:
        return []

    # First pass: determine table dimensions
    max_cols = 0
    for row in rows:
        cols_in_row = 0
        for cell in row.find_all(["th", "td"]):
            colspan = int(cell.get("colspan", 1))
            cols_in_row += colspan
        max_cols = max(max_cols, cols_in_row)
        
    if max_cols == 0:
        return []

    # Initialize a 2D grid with None
    grid: list[list[str | None]] = [[None for _ in range(max_cols)] for _ in range(len(rows))]

    # Second pass: fill the grid
    for r, row in enumerate(rows):
        cells = row.find_all(["th", "td"])
        c = 0
        for cell in cells:
            # Find the next available column
            while c < max_cols and grid[r][c] is not None:
                c += 1
                
            if c >= max_cols:
                break # Should not happen if dimensions are calculated correctly
                
            colspan = int(cell.get("colspan", 1))
            rowspan = int(cell.get("rowspan", 1))
            text = _clean_text(cell.get_text(separator=" ", strip=True))
            
            # Fill the cell and spanned areas
            for i in range(rowspan):
                for j in range(colspan):
                    if r + i < len(rows) and c + j < max_cols:
                        grid[r + i][c + j] = text
            c += colspan

    # Ensure all None values are converted to empty strings just in case
    string_grid: list[list[str]] = [
        [cell if cell is not None else "" for cell in row] 
        for row in grid
    ]

    if not string_grid:
        return []

    # Use the first row as headers
    headers = string_grid[0]
    
    # Handle duplicate headers by appending a number
    seen: dict[str, int] = {}
    unique_headers = []
    for h in headers:
        if not h:
            h = "unknown"
        if h in seen:
            seen[h] += 1
            unique_headers.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            unique_headers.append(h)

    # Convert the rest to dictionaries
    result = []
    for row in string_grid[1:]:
        # Skip completely empty rows
        if not any(row):
            continue
            
        row_dict = {}
        for key, value in zip(unique_headers, row):
            row_dict[key] = value
        result.append(row_dict)

    return result
