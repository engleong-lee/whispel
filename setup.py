"""
Setup script for building Whispel Voice Transcriber as a macOS app.
"""
import sys
from setuptools import setup

# Increase recursion limit to handle complex dependencies
sys.setrecursionlimit(10000)

APP = ['voice_transcriber_debug.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': True,
    'iconfile': None,  # Add an .icns file here if you have one
    'plist': {
        'CFBundleName': 'Whispel',
        'CFBundleDisplayName': 'Whispel Voice Transcriber',
        'CFBundleIdentifier': 'com.whispel.voicetranscriber',
        'CFBundleVersion': '1.0.6',
        'CFBundleShortVersionString': '1.0.6',
        'LSMinimumSystemVersion': '10.15',
        'NSMicrophoneUsageDescription': 'This app needs microphone access to transcribe your speech.',
        'NSAppleEventsUsageDescription': 'This app uses AppleEvents to paste transcribed text.',
        'LSUIElement': True,  # This makes it a menu bar only app (no dock icon)
    },
    'packages': ['rumps', 'numpy', 'pyaudio', 'pyperclip', 'parakeet_mlx', 'pynput'],
    'includes': ['audio_recorder'],
    'excludes': ['tensorflow', 'torch', 'jax'],  # Exclude heavy ML frameworks that might cause recursion
    'resources': [],
    'optimize': 0,  # Disable optimization to avoid AST issues
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
    name='Whispel',
    version='1.0.0',
    description='Voice transcription app for macOS',
    author='Your Name',
    url='https://github.com/yourusername/whispel',
)