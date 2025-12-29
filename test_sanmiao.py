#!/usr/bin/env python3
"""
Test script for sanmiao package functionality, especially the civ parameter.
"""
import sys
import os

# Add the src directory to the path so we can import sanmiao
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import sanmiao

def test_basic_functionality():
    """Test basic functionality without civ parameter."""
    print("=" * 60)
    print("Test 1: Basic functionality (default civ=['c','j','k'])")
    print("=" * 60)
    test_input = "建安元年"
    result = sanmiao.cjk_date_interpreter(test_input, lang='en')
    print(f"Input: {test_input}")
    print(f"Result:\n{result}")
    print()

def test_civ_china_only():
    """Test with civ=['c'] (China only)."""
    print("=" * 60)
    print("Test 2: China only (civ=['c'])")
    print("=" * 60)
    test_input = "建安元年"  # Jian'an era, Chinese
    result = sanmiao.cjk_date_interpreter(test_input, lang='en', civ=['c'])
    print(f"Input: {test_input}")
    print(f"Result:\n{result}")
    print()

def test_civ_japan_only():
    """Test with civ=['j'] (Japan only)."""
    print("=" * 60)
    print("Test 3: Japan only (civ=['j'])")
    print("=" * 60)
    test_input = "建安元年"  # Jian'an era, should NOT match for Japan
    result = sanmiao.cjk_date_interpreter(test_input, lang='en', civ=['j'])
    print(f"Input: {test_input}")
    print(f"Result:\n{result}")
    print()

def test_civ_korea_only():
    """Test with civ=['k'] (Korea only)."""
    print("=" * 60)
    print("Test 4: Korea only (civ=['k'])")
    print("=" * 60)
    test_input = "建安元年"  # Jian'an era, should NOT match for Korea
    result = sanmiao.cjk_date_interpreter(test_input, lang='en', civ=['k'])
    print(f"Input: {test_input}")
    print(f"Result:\n{result}")
    print()

def test_civ_all():
    """Test with civ=['c','j','k'] (all civilizations)."""
    print("=" * 60)
    print("Test 5: All civilizations (civ=['c','j','k'])")
    print("=" * 60)
    test_input = "建安元年"
    result = sanmiao.cjk_date_interpreter(test_input, lang='en', civ=['c', 'j', 'k'])
    print(f"Input: {test_input}")
    print(f"Result:\n{result}")
    print()

def test_civ_single_string():
    """Test with civ='c' (single string instead of list)."""
    print("=" * 60)
    print("Test 6: Single string civ='c'")
    print("=" * 60)
    test_input = "建安元年"
    result = sanmiao.cjk_date_interpreter(test_input, lang='en', civ='c')
    print(f"Input: {test_input}")
    print(f"Result:\n{result}")
    print()

if __name__ == "__main__":
    try:
        test_basic_functionality()
        test_civ_china_only()
        test_civ_japan_only()
        test_civ_korea_only()
        test_civ_all()
        test_civ_single_string()
        print("=" * 60)
        print("All tests completed successfully!")
        print("=" * 60)
    except Exception as e:
        print(f"ERROR: Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

