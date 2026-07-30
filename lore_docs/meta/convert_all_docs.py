#!/usr/bin/env python3
"""
Convert ALL Office documents to Markdown for easier access
"""

import os
import sys
import zipfile
import xml.etree.ElementTree as ET
import csv
import re
from pathlib import Path

def extract_docx_text(docx_path):
    """Extract text from a .docx file"""
    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            # Read the main document XML
            with z.open('word/document.xml') as xml_file:
                tree = ET.parse(xml_file)
                root = tree.getroot()
                
                # Define namespaces
                namespaces = {
                    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
                }
                
                # Extract all text
                paragraphs = []
                for paragraph in root.findall('.//w:p', namespaces):
                    texts = []
                    for text_elem in paragraph.findall('.//w:t', namespaces):
                        if text_elem.text:
                            texts.append(text_elem.text)
                    if texts:
                        paragraphs.append(''.join(texts))
                
                return '\n\n'.join(paragraphs)
    except Exception as e:
        return f"Error reading {docx_path}: {str(e)}"

def extract_xlsx_text(xlsx_path):
    """Extract text from an .xlsx file"""
    try:
        with zipfile.ZipFile(xlsx_path, 'r') as z:
            # Get shared strings if they exist
            shared_strings = []
            if 'xl/sharedStrings.xml' in z.namelist():
                with z.open('xl/sharedStrings.xml') as xml_file:
                    tree = ET.parse(xml_file)
                    root = tree.getroot()
                    for si in root.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si'):
                        text = ''.join(t.text for t in si.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t') if t.text)
                        shared_strings.append(text)
            
            # Get sheet names
            sheets = []
            with z.open('xl/workbook.xml') as xml_file:
                tree = ET.parse(xml_file)
                root = tree.getroot()
                for sheet in root.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet'):
                    sheets.append(sheet.get('name'))
            
            # Extract data from first few sheets
            all_content = []
            for i, sheet_name in enumerate(sheets[:3], 1):  # Limit to first 3 sheets
                sheet_file = f'xl/worksheets/sheet{i}.xml'
                if sheet_file in z.namelist():
                    all_content.append(f"## Sheet: {sheet_name}\n")
                    with z.open(sheet_file) as xml_file:
                        tree = ET.parse(xml_file)
                        root = tree.getroot()
                        
                        rows = []
                        for row in root.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row'):
                            cells = []
                            for cell in row.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c'):
                                value_elem = cell.find('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
                                if value_elem is not None and value_elem.text:
                                    if cell.get('t') == 's':  # Shared string
                                        idx = int(value_elem.text)
                                        if idx < len(shared_strings):
                                            cells.append(shared_strings[idx])
                                    else:
                                        cells.append(value_elem.text)
                            if cells:
                                rows.append(' | '.join(cells))
                        
                        if rows:
                            all_content.append('\n'.join(rows[:50]))  # Limit to first 50 rows
            
            return '\n\n'.join(all_content)
    except Exception as e:
        return f"Error reading {xlsx_path}: {str(e)}"

def convert_file(input_path, output_dir):
    """Convert a single file to markdown"""
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    
    if input_path.suffix.lower() == '.docx':
        content = extract_docx_text(input_path)
        output_filename = input_path.stem + '.md'
    elif input_path.suffix.lower() in ['.xlsx', '.xls']:
        content = extract_xlsx_text(input_path)
        output_filename = input_path.stem + '.md'
    else:
        return False
    
    # Create output directory if needed
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Write markdown file
    output_path = output_dir / output_filename
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"# {input_path.stem}\n\n")
        f.write(f"*Converted from: {input_path.name}*\n\n")
        f.write(content)
    
    print(f"Converted: {input_path.name} -> {output_path}")
    return True

def main():
    # Find all Office files
    import subprocess
    result = subprocess.run(
        ['find', '/home/luminari/lore', '-type', 'f', '(', '-name', '*.xlsx', '-o', '-name', '*.docx', ')'],
        capture_output=True, text=True
    )
    
    all_files = [f for f in result.stdout.strip().split('\n') if f]
    
    print(f"Found {len(all_files)} Office files to convert")
    
    converted = 0
    failed = 0
    
    for file_path in all_files:
        try:
            # Determine output directory - keep same structure but add 'converted' folder
            file_path = Path(file_path)
            relative_path = file_path.relative_to('/home/luminari/lore')
            parent_dir = relative_path.parent
            output_dir = Path('/home/luminari/lore') / parent_dir / 'converted'
            
            if convert_file(file_path, output_dir):
                converted += 1
            else:
                failed += 1
        except Exception as e:
            print(f"Failed to convert {file_path}: {e}")
            failed += 1
    
    print(f"\nConversion complete: {converted} succeeded, {failed} failed")

if __name__ == '__main__':
    main()