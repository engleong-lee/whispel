"""
Runtime hook for MLX and parakeet_mlx modules
This adds the Resources directory to sys.path so MLX modules can be found
Also sets up HuggingFace cache directory for model files and FFmpeg PATH
"""
import sys
import os

def setup_mlx_environment():
    """Set up environment for MLX in PyInstaller bundle"""
    if not hasattr(sys, '_MEIPASS'):
        return
    
    print("🔍 DEBUG: Setting up MLX environment for bundled app...")
    bundle_dir = sys._MEIPASS
    print(f"🔍 DEBUG: Bundle directory: {bundle_dir}")
    
    # Get the app bundle's Resources directory
    app_contents_dir = os.path.dirname(bundle_dir)
    resources_dir = os.path.join(app_contents_dir, 'Resources')
    
    print(f"🔍 DEBUG: Looking for Resources directory at: {resources_dir}")
    
    if os.path.exists(resources_dir):
        sys.path.insert(0, resources_dir)
        print(f"🔍 DEBUG: Added Resources directory to Python path: {resources_dir}")
        
        # Set up MLX library paths
        mlx_dirs_to_check = [
            os.path.join(resources_dir, 'mlx', 'lib'),
            os.path.join(resources_dir, 'mlx'),
            os.path.join(bundle_dir, 'mlx', 'lib'),
            os.path.join(bundle_dir, 'mlx')
        ]
        
        for mlx_lib_dir in mlx_dirs_to_check:
            if os.path.exists(mlx_lib_dir):
                current_path = os.environ.get('DYLD_LIBRARY_PATH', '')
                if current_path:
                    os.environ['DYLD_LIBRARY_PATH'] = f"{mlx_lib_dir}:{current_path}"
                else:
                    os.environ['DYLD_LIBRARY_PATH'] = mlx_lib_dir
                print(f"🔍 DEBUG: Added MLX lib directory to DYLD_LIBRARY_PATH: {mlx_lib_dir}")
                break
        else:
            print("🔍 DEBUG: No MLX lib directory found")
    else:
        print(f"🔍 DEBUG: Resources directory not found: {resources_dir}")
    
    # Add bundle directory to PATH for FFmpeg and other tools
    current_path = os.environ.get('PATH', '')
    if current_path:
        os.environ['PATH'] = f"{bundle_dir}:{current_path}"
    else:
        os.environ['PATH'] = bundle_dir
    print(f"🔍 DEBUG: Added bundle directory to PATH: {bundle_dir}")
    
    # Set up HuggingFace cache directory
    home_dir = os.path.expanduser('~')
    hf_cache_dir = os.path.join(home_dir, '.cache', 'huggingface')
    if not os.path.exists(hf_cache_dir):
        try:
            os.makedirs(hf_cache_dir, exist_ok=True)
            print(f"🔍 DEBUG: Created HuggingFace cache directory: {hf_cache_dir}")
        except Exception as e:
            print(f"🔍 DEBUG: Could not create HuggingFace cache directory: {e}")
    
    # Set HuggingFace environment variables
    os.environ['HF_HOME'] = hf_cache_dir
    os.environ['TRANSFORMERS_CACHE'] = hf_cache_dir
    print(f"🔍 DEBUG: Set HuggingFace cache to: {hf_cache_dir}")
    
    print("🔍 DEBUG: MLX environment setup complete")

# Run the setup
setup_mlx_environment()