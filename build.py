#!/usr/bin/env python3
"""
Build script for Whispel - generates PyInstaller spec file and builds the app
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path

def find_package_path(package_name):
    """Find the path to a Python package"""
    try:
        import importlib.util
        spec = importlib.util.find_spec(package_name)
        if spec and spec.origin:
            # Get the package directory (not the __init__.py file)
            package_path = os.path.dirname(spec.origin)
            return package_path
    except ImportError:
        pass
    
    # Fallback: try using pip show
    try:
        result = subprocess.run([sys.executable, '-m', 'pip', 'show', package_name], 
                              capture_output=True, text=True, check=True)
        for line in result.stdout.split('\n'):
            if line.startswith('Location:'):
                location = line.split(':', 1)[1].strip()
                return os.path.join(location, package_name.replace('-', '_'))
    except subprocess.CalledProcessError:
        pass
    
    return None

def generate_spec_file():
    """Generate Whispel.spec from template with correct paths"""
    print("🔍 Finding package paths...")
    
    # Find package paths
    parakeet_path = find_package_path('parakeet_mlx')
    mlx_path = find_package_path('mlx')
    
    if not parakeet_path:
        print("❌ Could not find parakeet_mlx package path")
        print("   Make sure parakeet_mlx is installed: pip install parakeet_mlx")
        return False
        
    if not mlx_path:
        print("❌ Could not find mlx package path")
        print("   Make sure mlx is installed: pip install mlx")
        return False
    
    print(f"✅ Found parakeet_mlx at: {parakeet_path}")
    print(f"✅ Found mlx at: {mlx_path}")
    
    # Read template
    template_path = Path('Whispel.spec.template')
    if not template_path.exists():
        print("❌ Whispel.spec.template not found")
        return False
    
    with open(template_path, 'r') as f:
        template_content = f.read()
    
    # Replace placeholders
    spec_content = template_content.replace('{{PARAKEET_MLX_PATH}}', parakeet_path)
    spec_content = spec_content.replace('{{MLX_PATH}}', mlx_path)
    
    # Write spec file
    with open('Whispel.spec', 'w') as f:
        f.write(spec_content)
    
    print("✅ Generated Whispel.spec with correct paths")
    return True

def build_app():
    """Build the app using PyInstaller"""
    print("🔨 Building Whispel app...")
    
    try:
        subprocess.run([sys.executable, '-m', 'PyInstaller', 'Whispel.spec'], check=True)
        print("✅ Build completed successfully!")
        print("📦 App bundle created at: dist/Whispel.app")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed: {e}")
        return False

def main():
    """Main build process"""
    print("🚀 Starting Whispel build process...")
    
    # Check requirements
    if not shutil.which('python'):
        print("❌ Python not found in PATH")
        return 1
    
    # Generate spec file
    if not generate_spec_file():
        return 1
    
    # Build app
    if not build_app():
        return 1
    
    print("🎉 Build process completed successfully!")
    return 0

if __name__ == '__main__':
    sys.exit(main())