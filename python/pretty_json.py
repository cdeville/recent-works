#!/usr/bin/env python3
"""
Simple CLI tool to pretty-format JSON files in place.
"""

import argparse
import json
import sys


def pretty_format_json(filename):
    """
    Read a JSON file, format it prettily, and overwrite it. 
    
    Args:
        filename: Path to the JSON file to format
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Read the JSON file
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Write it back with pretty formatting
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
            f.write('\n')  # Add trailing newline
        
        print(f"✓ Successfully formatted {filename}")
        return True
        
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found", file=sys.stderr)
        return False
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{filename}': {e}", file=sys.stderr)
        return False
    except PermissionError:
        print(f"Error: Permission denied when accessing '{filename}'", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return False


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description='Pretty-format a JSON file and overwrite it in place.'
    )
    parser.add_argument(
        '-f', '--file',
        required=True,
        help='JSON file to format'
    )
    
    args = parser.parse_args()
    
    success = pretty_format_json(args.file)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
