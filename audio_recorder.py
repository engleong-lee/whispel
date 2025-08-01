import pyaudio
import wave
import threading
import time
import os
import sys
import tempfile
import numpy as np
from datetime import datetime
from typing import Callable, Optional


class AudioRecorder:
    def __init__(self, 
                 sample_rate: int = 44100,
                 chunk_size: int = 1024,
                 channels: int = 1,
                 format: int = pyaudio.paInt16,
                 debug_mode: bool = False,
                 max_recording_time: Optional[float] = 60.0,
                 stop_callback: Optional[Callable[[str], None]] = None):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.channels = channels
        self.format = format
        self.debug_mode = debug_mode
        self.max_recording_time = max_recording_time
        self.stop_callback = stop_callback
        self.is_recording = False
        self.frames = []
        self.stream = None
        self.start_time = 0
        self.audio = None
        self.chunk_counter = 0
        self._lock = threading.Lock()
        
        # Debug audio monitoring
        self.debug_sample_count = 0
        self.debug_peak_level = 0.0
        self.debug_rms_level = 0.0
        self.debug_last_report_time = 0
        self._was_debug_enabled = debug_mode
        
        self._initialize_audio()
        
        if self.debug_mode:
            self._setup_debug_directory()
    
    def _initialize_audio(self):
        """Initialize PyAudio instance if not already initialized."""
        if self.audio is None:
            try:
                # Apply PyAudio context fixes for environment differences
                self._apply_pyaudio_context_fixes()
                
                self.audio = pyaudio.PyAudio()
                if self.debug_mode:
                    self._debug_environment_differences()
                    self._debug_audio_devices()
                    self._debug_microphone_permissions()
                    self._debug_preferred_audio_device()
                return True
            except Exception as e:
                print(f"Failed to initialize PyAudio: {str(e)}")
                self.audio = None
                return False
        return True
    
    def _apply_pyaudio_context_fixes(self):
        """Apply fixes to help PyAudio work consistently between terminal and app launch"""
        try:
            import os
            
            # Force reinitialize audio subsystem environment
            audio_env_fixes = {
                'PYAUDIO_DEBUG': '0',  # Disable PyAudio debug output
                'PORTAUDIO_IGNORE_ENV': '0',  # Don't ignore environment variables
                'ALSA_CARD': '0',  # Default ALSA card (helps with some setups)
            }
            
            for var, value in audio_env_fixes.items():
                if not os.environ.get(var):
                    os.environ[var] = value
                    if self.debug_mode:
                        print(f"🔍 DEBUG: Set PyAudio env {var}={value}")
            
            # Try to clear any stale audio state by forcing a system call
            try:
                import subprocess
                # This can help reset audio device state
                subprocess.run(['pkill', '-f', 'coreaudiod'], capture_output=True, timeout=1)
                if self.debug_mode:
                    print("🔍 DEBUG: Attempted to refresh Core Audio daemon")
            except:
                # Ignore errors - this is optional
                pass
                
        except Exception as e:
            if self.debug_mode:
                print(f"🔍 DEBUG: PyAudio context fixes failed: {e}")
    
    def _debug_preferred_audio_device(self):
        """Debug: Show the preferred audio input device"""
        if not self.debug_mode or not self.audio:
            return
        
        try:
            # Find USB audio devices specifically
            usb_devices = []
            device_count = self.audio.get_device_count()
            
            for i in range(device_count):
                device_info = self.audio.get_device_info_by_index(i)
                if (device_info['maxInputChannels'] > 0 and 
                    ('usb' in device_info['name'].lower() or 
                     'headset' in device_info['name'].lower() or
                     'microphone' in device_info['name'].lower())):
                    usb_devices.append((i, device_info))
            
            if usb_devices:
                print(f"🔍 DEBUG: Found {len(usb_devices)} USB/external audio input devices:")
                for i, device_info in usb_devices:
                    print(f"    Device {i}: {device_info['name']}")
                    
                # Test the first USB device
                test_device = usb_devices[0]
                print(f"🔍 DEBUG: Testing device: {test_device[1]['name']}")
                self._test_audio_device(test_device[0])
            else:
                print("🔍 DEBUG: No USB/external audio devices found")
                
        except Exception as e:
            print(f"🔍 DEBUG: Error finding preferred audio device: {e}")
    
    def _test_audio_device(self, device_index):
        """Debug: Test if a specific audio device works"""
        if not self.debug_mode:
            return
        
        try:
            test_stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=1024
            )
            
            # Try to read a small amount of data
            data = test_stream.read(1024, exception_on_overflow=False)
            test_stream.close()
            
            # Analyze the test data
            import numpy as np
            audio_data = np.frombuffer(data, dtype=np.int16)
            peak = np.max(np.abs(audio_data)) if len(audio_data) > 0 else 0
            
            print(f"🔍 DEBUG: Device test result - Peak level: {peak} ({'✅ Working' if peak > 0 else '⚠️ Silent'})")
            
        except Exception as e:
            print(f"🔍 DEBUG: Device test failed: {e}")
    
    def _find_preferred_input_device(self):
        """Find the best input device to use (prefer USB/external devices)"""
        if not self.audio:
            return None
        
        try:
            device_count = self.audio.get_device_count()
            
            # First priority: USB/external devices
            usb_devices = []
            # Second priority: Built-in microphones
            builtin_devices = []
            
            for i in range(device_count):
                try:
                    device_info = self.audio.get_device_info_by_index(i)
                    if device_info['maxInputChannels'] > 0:
                        device_name = device_info['name'].lower()
                        
                        # Prioritize USB and external devices
                        if any(keyword in device_name for keyword in 
                               ['usb', 'headset', 'external', 'blue', 'wireless']):
                            usb_devices.append((i, device_info))
                        elif any(keyword in device_name for keyword in 
                                ['built-in', 'internal', 'macbook']):
                            builtin_devices.append((i, device_info))
                        else:
                            # Unknown device type, treat as potential external device
                            usb_devices.append((i, device_info))
                            
                except Exception as e:
                    if self.debug_mode:
                        print(f"🔍 DEBUG: Error checking device {i}: {e}")
                    continue
            
            # Choose the best device
            if usb_devices:
                best_device = usb_devices[0][0]  # First USB device
                if self.debug_mode:
                    print(f"🔍 DEBUG: Selected USB/external device: {usb_devices[0][1]['name']}")
                return best_device
            elif builtin_devices:
                best_device = builtin_devices[0][0]  # First built-in device
                if self.debug_mode:
                    print(f"🔍 DEBUG: Selected built-in device: {builtin_devices[0][1]['name']}")
                return best_device
            
            # Fallback: use default device
            if self.debug_mode:
                print("🔍 DEBUG: Using default input device")
            return None  # Let PyAudio choose default
            
        except Exception as e:
            if self.debug_mode:
                print(f"🔍 DEBUG: Error finding preferred device: {e}")
            return None
    
    def _debug_audio_devices(self):
        """Debug: List all available audio input devices"""
        if not self.debug_mode or not self.audio:
            return
        
        try:
            device_count = self.audio.get_device_count()
            print(f"🔍 DEBUG: Found {device_count} audio devices:")
            
            input_devices = []
            for i in range(device_count):
                device_info = self.audio.get_device_info_by_index(i)
                if device_info['maxInputChannels'] > 0:
                    input_devices.append((i, device_info))
                    print(f"🔍 DEBUG: Input Device {i}: {device_info['name']}")
                    print(f"    Sample Rate: {device_info['defaultSampleRate']} Hz")
                    print(f"    Input Channels: {device_info['maxInputChannels']}")
                    print(f"    Host API: {self.audio.get_host_api_info_by_index(device_info['hostApi'])['name']}")
            
            # Show default input device
            try:
                default_input = self.audio.get_default_input_device_info()
                print(f"🔍 DEBUG: Default input device: {default_input['name']} (index {default_input['index']})")
            except Exception as e:
                print(f"🔍 DEBUG: No default input device: {e}")
                
        except Exception as e:
            print(f"🔍 DEBUG: Error enumerating audio devices: {e}")
    
    def _debug_microphone_permissions(self):
        """Debug: Check microphone permissions"""
        if not self.debug_mode:
            return
        
        try:
            # Try to create a test stream to check permissions
            test_stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=1024
            )
            test_stream.close()
            print("🔍 DEBUG: Microphone permission: ✅ GRANTED")
        except Exception as e:
            print(f"🔍 DEBUG: Microphone permission: ❌ DENIED or ERROR - {e}")
            print("🔍 DEBUG: Check System Settings > Privacy & Security > Microphone")
    
    def _debug_environment_differences(self):
        """Debug: Show environment differences that might affect audio"""
        if not self.debug_mode:
            return
        
        import os
        
        print("🔍 DEBUG: === ENVIRONMENT ANALYSIS ===")
        
        # Check if we're running from terminal vs app bundle
        if hasattr(sys, '_MEIPASS'):
            print("🔍 DEBUG: Running from PyInstaller bundle")
        else:
            print("🔍 DEBUG: Running from source")
        
        # Check important environment variables
        important_env_vars = [
            'PATH', 'DYLD_LIBRARY_PATH', 'PYTHONPATH', 
            'HOME', 'USER', 'SHELL', 'TERM',
            'AUDIO_DRIVER', 'COREAUDIO_DRIVER'
        ]
        
        for var in important_env_vars:
            value = os.environ.get(var, '<NOT SET>')
            if var == 'PATH' and len(value) > 200:
                # Truncate very long PATH for readability
                value = value[:200] + f"... (total length: {len(os.environ.get(var, ''))}"
            print(f"🔍 DEBUG: {var}: {value}")
        
        # Check audio-related system info
        print("🔍 DEBUG: === AUDIO SYSTEM INFO ===")
        try:
            import platform
            print(f"🔍 DEBUG: Platform: {platform.platform()}")
            print(f"🔍 DEBUG: Python: {platform.python_version()}")
            print(f"🔍 DEBUG: Architecture: {platform.machine()}")
        except Exception as e:
            print(f"🔍 DEBUG: Error getting platform info: {e}")
        
        # Check working directory
        print(f"🔍 DEBUG: Working directory: {os.getcwd()}")
        
        # Check if terminal detection works
        try:
            terminal_detected = os.isatty(sys.stdout.fileno())
            print(f"🔍 DEBUG: Terminal detected: {terminal_detected}")
        except:
            print("🔍 DEBUG: Terminal detection failed")
        
        print("🔍 DEBUG: === END ENVIRONMENT ANALYSIS ===")
        
    def _setup_debug_directory(self):
        self.debug_dir = os.path.join(os.path.dirname(__file__), "debug_audio")
        if not os.path.exists(self.debug_dir):
            os.makedirs(self.debug_dir)
        
    def start_recording(self, callback: Optional[Callable[[str], None]] = None, 
                       ready_callback: Optional[Callable[[], None]] = None):
        with self._lock:
            if self.is_recording or not self._initialize_audio():
                return False
            
            self.is_recording = True
            self.frames = []
            self.chunk_counter = 0
            self.start_time = time.time()
        
        return self._start_recording_internal(callback, ready_callback)
    
    def _start_recording_internal(self, callback: Optional[Callable[[str], None]] = None,
                                 ready_callback: Optional[Callable[[], None]] = None):
        """Start recording using PyAudio's stream callback."""
        try:
            # Store the callback for chunk processing if provided
            self.chunk_callback = callback
            self.chunk_frames_target = int(self.sample_rate * 3.0)  # Default 3 second chunks
            self.current_chunk_frames = 0
            self.current_chunk_data = []
            
            # Try to open stream with explicit device selection for better compatibility
            stream_params = {
                'format': self.format,
                'channels': self.channels,
                'rate': self.sample_rate,
                'input': True,
                'frames_per_buffer': self.chunk_size,
                'stream_callback': self._audio_callback
            }
            
            # Try to find and use a preferred audio device (USB/external first)
            preferred_device = self._find_preferred_input_device()
            if preferred_device is not None:
                stream_params['input_device_index'] = preferred_device
                if self.debug_mode:
                    device_info = self.audio.get_device_info_by_index(preferred_device)
                    print(f"🔍 DEBUG: Using preferred device {preferred_device}: {device_info['name']}")
            
            self.stream = self.audio.open(**stream_params)
            
            # Start the timer for max recording time if specified
            if self.max_recording_time is not None:
                self._start_timeout_timer()
            
            if ready_callback:
                ready_callback()
                
            return True
        except Exception as e:
            print(f"Start recording error: {str(e)}")
            self._cleanup()
            with self._lock:
                self.is_recording = False
            return False
    
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Audio stream callback that processes chunks for real-time transcription."""
        with self._lock:
            if self.is_recording:
                self.frames.append(in_data)
                
                # Debug: Monitor audio levels
                if self.debug_mode:
                    self._debug_monitor_audio_levels(in_data, frame_count)
                
                # Handle chunk processing if callback is provided
                if hasattr(self, 'chunk_callback') and self.chunk_callback:
                    self.current_chunk_data.append(in_data)
                    self.current_chunk_frames += frame_count
                    
                    # Check if we've collected enough frames for a chunk
                    if self.current_chunk_frames >= self.chunk_frames_target:
                        # Process the chunk in a separate thread to avoid blocking audio
                        def process_chunk():
                            try:
                                temp_file = self._save_chunk_to_temp_file(self.current_chunk_data)
                                self.chunk_callback(temp_file)
                            except Exception as e:
                                print(f"Chunk processing error: {e}")
                        
                        threading.Thread(target=process_chunk, daemon=True).start()
                        
                        # Reset for next chunk
                        self.current_chunk_data = []
                        self.current_chunk_frames = 0
        
        return (in_data, pyaudio.paContinue)
    
    def _debug_monitor_audio_levels(self, in_data, frame_count):
        """Debug: Monitor audio levels during recording"""
        if not self.debug_mode:
            return
        
        try:
            # Convert audio data to numpy array for analysis
            audio_data = np.frombuffer(in_data, dtype=np.int16)
            
            # Calculate peak and RMS levels
            if len(audio_data) > 0:
                peak = np.max(np.abs(audio_data))
                rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))
                
                # Update running peak and RMS
                self.debug_peak_level = max(self.debug_peak_level, peak)
                self.debug_rms_level = max(self.debug_rms_level, rms)  # Use max RMS as indicator
                self.debug_sample_count += frame_count
                
                # Report levels every 2 seconds
                current_time = time.time()
                if current_time - self.debug_last_report_time >= 2.0:
                    peak_pct = (self.debug_peak_level / 32767.0) * 100  # Convert to percentage
                    rms_pct = (self.debug_rms_level / 32767.0) * 100
                    
                    # Create simple level meter
                    level_bars = int(peak_pct / 5)  # One bar per 5%
                    level_meter = "█" * level_bars + "░" * (20 - level_bars)
                    
                    print(f"🔍 DEBUG: Audio Level [{level_meter}] Peak: {peak_pct:.1f}% RMS: {rms_pct:.1f}%")
                    
                    # Check if we're getting any audio
                    if self.debug_peak_level < 100:  # Very low threshold
                        print("🔍 DEBUG: ⚠️ Audio levels very low - check microphone!")
                    
                    # Reset for next period
                    self.debug_peak_level = 0.0
                    self.debug_rms_level = 0.0
                    self.debug_last_report_time = current_time
                    
        except Exception as e:
            # Don't let debug monitoring crash the audio callback
            pass
    
    def _debug_verify_audio_file(self, filepath, original_audio_data):
        """Debug: Verify that the saved audio file contains actual audio data"""
        if not self.debug_mode and not (hasattr(self, '_was_debug_enabled') and self._was_debug_enabled):
            return
        
        try:
            # Check file size
            file_size = os.path.getsize(filepath)
            print(f"🔍 DEBUG: Audio file saved: {filepath}")
            print(f"🔍 DEBUG: File size: {file_size:,} bytes")
            
            # Analyze the saved file
            with wave.open(filepath, 'rb') as wf:
                frames = wf.getnframes()
                sample_rate = wf.getframerate()
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                duration = frames / sample_rate
                
                print(f"🔍 DEBUG: Audio properties:")
                print(f"    Duration: {duration:.2f} seconds")
                print(f"    Frames: {frames:,}")
                print(f"    Sample Rate: {sample_rate} Hz")
                print(f"    Channels: {channels}")
                print(f"    Sample Width: {sample_width} bytes")
                
                # Read and analyze first few seconds of audio data
                wf.rewind()
                sample_data = wf.readframes(min(frames, sample_rate * 2))  # First 2 seconds max
                
                if sample_data:
                    audio_array = np.frombuffer(sample_data, dtype=np.int16)
                    peak_value = np.max(np.abs(audio_array))
                    rms_value = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
                    
                    peak_pct = (peak_value / 32767.0) * 100
                    rms_pct = (rms_value / 32767.0) * 100
                    
                    print(f"🔍 DEBUG: Audio analysis:")
                    print(f"    Peak level: {peak_pct:.1f}% ({peak_value})")
                    print(f"    RMS level: {rms_pct:.1f}% ({rms_value:.0f})")
                    
                    # Check for silence
                    if peak_value < 50:  # Very low threshold
                        print("🔍 DEBUG: ⚠️ WARNING: Audio file appears to be mostly silent!")
                        print("🔍 DEBUG: This indicates microphone input is not working properly")
                    elif peak_value < 500:
                        print("🔍 DEBUG: ⚠️ WARNING: Audio levels are very low")
                        print("🔍 DEBUG: Check microphone sensitivity and input levels")
                    else:
                        print("🔍 DEBUG: ✅ Audio file contains usable audio data")
                        
                else:
                    print("🔍 DEBUG: ❌ ERROR: No audio data in file!")
                    
        except Exception as e:
            print(f"🔍 DEBUG: Error verifying audio file: {e}")
    
    def _start_timeout_timer(self):
        """Start timeout timer for automatic stop."""
        def timer():
            time.sleep(self.max_recording_time)
            with self._lock:
                if self.is_recording:
                    audio_file = self.stop_recording()
                    if self.stop_callback and audio_file:
                        self.stop_callback(audio_file)
        
        timer_thread = threading.Thread(target=timer)
        timer_thread.daemon = True
        timer_thread.start()
    
    def stop_recording(self, final_delay: float = 2.0) -> Optional[str]:
        with self._lock:
            if not self.is_recording:
                return None
            self.is_recording = False
        
        # Add delay to capture final words
        if final_delay > 0:
            time.sleep(final_delay)
        
        try:
            # Clean up stream resources
            self._cleanup()
            
            # Check recording duration and save
            if self.frames:
                duration = (len(self.frames) * self.chunk_size) / self.sample_rate
                if duration < 1.0:
                    raise ValueError("Recording must be at least 1 second long")
                
                return self._save_to_temp_file(self.frames)
            return None
        except Exception as e:
            print(f"Stop recording error: {str(e)}")
            return None
    
    def _save_chunk_to_temp_file(self, chunk_data: list) -> str:
        self.chunk_counter += 1
        
        if self.debug_mode:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_filename = f"chunk_{timestamp}_{self.chunk_counter:03d}.wav"
            temp_path = os.path.join(self.debug_dir, temp_filename)
        else:
            temp_filename = f"temp_audio_{int(time.time() * 1000)}.wav"
            temp_path = os.path.join(os.path.dirname(__file__), temp_filename)
        
        with wave.open(temp_path, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.audio.get_sample_size(self.format))
            wf.setframerate(self.sample_rate)
            wf.writeframes(b''.join(chunk_data))
        
        return temp_path
    
    def _save_to_temp_file(self, audio_data: list) -> str:
        """Save audio data to temporary file (modern approach)."""
        if self.debug_mode:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"final_{timestamp}.wav"
            filepath = os.path.join(self.debug_dir, filename)
            with wave.open(filepath, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(self.audio.get_sample_size(self.format))
                wf.setframerate(self.sample_rate)
                wf.writeframes(b''.join(audio_data))
            
            # Debug: Verify audio file
            if self.debug_mode:
                self._debug_verify_audio_file(filepath, audio_data)
                
            return filepath
        else:
            # Use tempfile for better resource management
            temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_filename = temp_file.name
            temp_file.close()
            
            with wave.open(temp_filename, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(self.audio.get_sample_size(self.format))
                wf.setframerate(self.sample_rate)
                wf.writeframes(b''.join(audio_data))
            
            # Debug: Verify audio file even in non-debug mode if debug was enabled during recording
            if hasattr(self, '_was_debug_enabled') and self._was_debug_enabled:
                self._debug_verify_audio_file(temp_filename, audio_data)
            
            return temp_filename
    
    
    def _cleanup(self):
        """Internal method to clean up stream resources."""
        try:
            if self.stream and hasattr(self.stream, 'is_active') and self.stream.is_active():
                self.stream.stop_stream()
                self.stream.close()
        except Exception as e:
            print(f"Stream cleanup error: {str(e)}")
        finally:
            self.stream = None
    
    def cleanup_temp_files(self):
        """Clean up temporary audio files."""
        if not self.debug_mode:
            current_dir = os.path.dirname(__file__)
            for file in os.listdir(current_dir):
                if file.startswith("temp_audio_") and file.endswith(".wav"):
                    try:
                        os.remove(os.path.join(current_dir, file))
                    except OSError:
                        pass
    
    def get_recording_duration(self) -> float:
        """Get the duration of the current recording."""
        if not self.is_recording:
            return 0
        return time.time() - self.start_time
                        
    def get_debug_directory(self) -> Optional[str]:
        """Get debug directory path if debug mode is enabled."""
        return self.debug_dir if self.debug_mode else None
    
    def __del__(self):
        """Clean up resources when object is deleted."""
        try:
            with self._lock:
                if self.is_recording:
                    self.is_recording = False
            
            self._cleanup()
            
            if hasattr(self, 'audio') and self.audio:
                self.audio.terminate()
                
            if not self.debug_mode:
                self.cleanup_temp_files()
        except Exception as e:
            print(f"Cleanup error in destructor: {str(e)}")