import rumps
import threading
import os
import pyperclip
import sys
import logging
from audio_recorder import AudioRecorder
from pynput.keyboard import Key, Controller
from pynput import keyboard

# Try to import MLX components, but gracefully handle failures
try:
    from parakeet_mlx import from_pretrained
    import mlx.core as mx
    MLX_AVAILABLE = True
    print("✅ MLX components loaded successfully")
except ImportError as e:
    print(f"❌ MLX import failed: {e}")
    MLX_AVAILABLE = False
    from_pretrained = None
except Exception as e:
    print(f"❌ MLX import failed: {e}")
    MLX_AVAILABLE = False
    from_pretrained = None


class VoiceTranscriber(rumps.App):
    def __init__(self):
        super(VoiceTranscriber, self).__init__("🎤")
        self.title = "🎤"  # Just the icon
        print("🚀 Initializing Whispel Voice Transcriber...")
        
        self.model = None
        self.recorder = None  
        self.is_recording = False
        self.transcribed_text = ""
        self.debug_mode = False
        self.auto_copy = True
        self.auto_paste = True  # Auto-paste after recording
        self.keyboard = Controller()  # For simulating key presses
        
        # File logging setup for debug mode
        self.debug_log_file = None
        self.original_stdout = None
        self.original_stderr = None
        
        # Initialize audio environment for consistent behavior
        self._initialize_audio_environment()
        
        print("📋 Setting up menu...")
        self.setup_menu()
        
        print("⌨️ Setting up hotkey...")
        self.setup_hotkey()
        
        print("🎙️ Initializing recorder...")
        self.init_recorder()
        
        if MLX_AVAILABLE:
            print("🤖 Loading ML model...")
            self.update_status("Loading model...")
            self.load_model()
        else:
            print("⚠️ MLX not available - transcription will not work")
            self.model = "UNAVAILABLE"
            self.update_status("MLX unavailable")
        
        print("✅ Whispel initialization complete!")
    
    def setup_menu(self):
        # Create menu items with essential options
        self.record_menu_item = rumps.MenuItem("🎤 Start (⌥ Space)", callback=self.toggle_recording)
        self.auto_copy_menu = rumps.MenuItem("Auto-copy to clipboard", callback=self.toggle_auto_copy)
        self.auto_paste_menu = rumps.MenuItem("Auto-paste after recording", callback=self.toggle_auto_paste)
        self.debug_mode_menu = rumps.MenuItem("Debug mode", callback=self.toggle_debug_mode)
        self.status_menu = rumps.MenuItem("Status: Initializing...", callback=None)
        self.permissions_menu = rumps.MenuItem("🔧 Enable Auto-Paste", callback=self.open_accessibility_settings)
        
        # Set initial menu state
        self.auto_copy_menu.state = 1 if self.auto_copy else 0
        self.auto_paste_menu.state = 1 if self.auto_paste else 0
        self.debug_mode_menu.state = 0  # Debug mode starts off
        
        self.menu = [
            self.status_menu,
            None,
            self.record_menu_item,
            None,  # separator
            self.auto_copy_menu,
            self.auto_paste_menu,
            None,  # separator
            self.permissions_menu,
            self.debug_mode_menu
        ]
    
    def update_status(self, status):
        """Update the status menu item"""
        self.status_menu.title = f"Status: {status}"
        print(f"📊 Status: {status}")
    
    def setup_debug_logging(self):
        """Set up file logging when debug mode is enabled"""
        if self.debug_log_file is not None:
            return  # Already set up
        
        try:
            log_path = os.path.expanduser("~/Desktop/whispel_debug.log")
            self.debug_log_file = open(log_path, 'w')
            
            # Store original stdout/stderr
            self.original_stdout = sys.stdout
            self.original_stderr = sys.stderr
            
            # Create a custom logger that writes to both file and original stdout
            class DebugLogger:
                def __init__(self, file_handle, original_stream):
                    self.file = file_handle
                    self.original = original_stream
                
                def write(self, text):
                    self.file.write(text)
                    self.file.flush()
                    # Also write to original stream if it's available (terminal mode)
                    if self.original:
                        try:
                            self.original.write(text)
                            self.original.flush()
                        except:
                            pass  # Ignore errors when no terminal
                
                def flush(self):
                    self.file.flush()
                    if self.original:
                        try:
                            self.original.flush()
                        except:
                            pass
            
            # Redirect stdout and stderr to our logger
            sys.stdout = DebugLogger(self.debug_log_file, self.original_stdout)
            sys.stderr = DebugLogger(self.debug_log_file, self.original_stderr)
            
            print(f"🐛 Debug logging started: {log_path}")
            print(f"🐛 App started at: {threading.current_thread().name}")
            
        except Exception as e:
            print(f"❌ Failed to set up debug logging: {e}")
    
    def teardown_debug_logging(self):
        """Clean up file logging when debug mode is disabled"""
        if self.debug_log_file is None:
            return  # Not set up
        
        try:
            print("🐛 Debug logging stopped")
            
            # Restore original stdout/stderr
            if self.original_stdout:
                sys.stdout = self.original_stdout
            if self.original_stderr:
                sys.stderr = self.original_stderr
            
            # Close log file
            self.debug_log_file.close()
            self.debug_log_file = None
            self.original_stdout = None
            self.original_stderr = None
            
        except Exception as e:
            print(f"❌ Failed to teardown debug logging: {e}")
    
    def _initialize_audio_environment(self):
        """Initialize audio environment for consistent behavior between terminal and double-click launch"""
        try:
            if self.debug_mode:
                print("🔍 DEBUG: Initializing audio environment...")
            
            # Set up environment variables that might be missing in Launch Services context
            self._setup_audio_environment_variables()
            
            # Initialize Core Audio frameworks
            self._initialize_core_audio_frameworks()
            
            # Configure audio session for USB microphone access
            self._configure_audio_session()
            
            if self.debug_mode:
                print("🔍 DEBUG: Audio environment initialization complete")
                
        except Exception as e:
            print(f"⚠️ Warning: Audio environment initialization failed: {e}")
            # Continue anyway - this shouldn't be fatal
    
    def _setup_audio_environment_variables(self):
        """Set up environment variables needed for audio to work properly"""
        try:
            import os
            import sys
            
            # Ensure basic environment variables are set
            if not os.environ.get('HOME'):
                os.environ['HOME'] = os.path.expanduser('~')
            
            # Set USER variable if missing (sometimes missing in Launch Services)
            if not os.environ.get('USER'):
                import getpass
                try:
                    os.environ['USER'] = getpass.getuser()
                except:
                    os.environ['USER'] = 'unknown'
            
            # Add system library paths that might be missing
            dyld_path = os.environ.get('DYLD_LIBRARY_PATH', '')
            system_paths = [
                '/usr/local/lib',
                '/opt/homebrew/lib',
                '/System/Library/Frameworks',
                '/Library/Frameworks',
                '/usr/lib',
                '/System/Library/PrivateFrameworks'
            ]
            
            for path in system_paths:
                if os.path.exists(path) and path not in dyld_path:
                    if dyld_path:
                        dyld_path = f"{path}:{dyld_path}"
                    else:
                        dyld_path = path
            
            if dyld_path:
                os.environ['DYLD_LIBRARY_PATH'] = dyld_path
            
            # Ensure PATH includes essential system directories
            current_path = os.environ.get('PATH', '')
            essential_paths = [
                '/usr/bin',
                '/bin',
                '/usr/sbin',
                '/sbin',
                '/usr/local/bin',
                '/opt/homebrew/bin'
            ]
            
            path_modified = False
            for path in essential_paths:
                if os.path.exists(path) and path not in current_path:
                    current_path = f"{path}:{current_path}" if current_path else path
                    path_modified = True
            
            if path_modified:
                os.environ['PATH'] = current_path
            
            # Set audio-specific environment variables that may help
            audio_env_vars = {
                'AUDIO_DRIVER': 'coreaudio',
                'COREAUDIO_DRIVER': '1',
                'PORTAUDIO_HOSTAPI': 'coreaudio'
            }
            
            for var, value in audio_env_vars.items():
                if not os.environ.get(var):
                    os.environ[var] = value
            
            if self.debug_mode:
                print(f"🔍 DEBUG: Set DYLD_LIBRARY_PATH: {dyld_path}")
                if path_modified:
                    print(f"🔍 DEBUG: Updated PATH with essential directories")
                print(f"🔍 DEBUG: Set audio environment variables: {list(audio_env_vars.keys())}")
                
        except Exception as e:
            if self.debug_mode:
                print(f"🔍 DEBUG: Error setting up environment variables: {e}")
    
    def _initialize_core_audio_frameworks(self):
        """Initialize Core Audio frameworks explicitly"""
        try:
            # Try to initialize AVFoundation framework
            try:
                import subprocess
                # This helps ensure audio frameworks are loaded
                subprocess.run(['system_profiler', 'SPAudioDataType'], 
                             capture_output=True, timeout=2)
                if self.debug_mode:
                    print("🔍 DEBUG: Core Audio frameworks initialized via system_profiler")
            except:
                # Fallback - just continue
                if self.debug_mode:
                    print("🔍 DEBUG: Could not run system_profiler, continuing...")
                    
        except Exception as e:
            if self.debug_mode:
                print(f"🔍 DEBUG: Core Audio framework initialization warning: {e}")
    
    def _configure_audio_session(self):
        """Configure audio session for proper USB microphone access"""
        try:
            # On macOS, we need to ensure the audio session is configured correctly
            # This is particularly important for USB audio devices
            
            # Set working directory to a known good location
            try:
                original_cwd = os.getcwd()
                home_dir = os.path.expanduser('~')
                os.chdir(home_dir)
                if self.debug_mode:
                    print(f"🔍 DEBUG: Changed working directory to: {home_dir}")
            except Exception as e:
                if self.debug_mode:
                    print(f"🔍 DEBUG: Could not change working directory: {e}")
            
            # Try to trigger Core Audio system initialization
            try:
                import subprocess
                # This command helps initialize the audio system and can resolve device issues
                subprocess.run(['audiodevice', 'input'], capture_output=True, timeout=2, text=True)
                if self.debug_mode:
                    print("🔍 DEBUG: Audio system queried successfully")
            except FileNotFoundError:
                # audiodevice command not available, try alternative
                try:
                    subprocess.run(['system_profiler', 'SPAudioDataType', '-timeout', '2'], 
                                 capture_output=True, timeout=3)
                    if self.debug_mode:
                        print("🔍 DEBUG: Audio system profiled successfully")
                except:
                    if self.debug_mode:
                        print("🔍 DEBUG: Could not profile audio system, continuing...")
            except Exception as e:
                if self.debug_mode:
                    print(f"🔍 DEBUG: Audio system query failed: {e}")
            
            # Force Python to recognize available audio devices by attempting PyAudio initialization
            try:
                import pyaudio
                temp_audio = pyaudio.PyAudio()
                device_count = temp_audio.get_device_count()
                if self.debug_mode:
                    print(f"🔍 DEBUG: PyAudio detected {device_count} audio devices")
                temp_audio.terminate()
            except Exception as e:
                if self.debug_mode:
                    print(f"🔍 DEBUG: PyAudio pre-initialization failed: {e}")
            
            # Set audio session preferences for USB devices
            try:
                # These environment variables can help with USB audio device detection
                additional_audio_env = {
                    'PA_ALSA_PLUGHW': '1',  # For better device compatibility
                    'PULSE_RUNTIME_PATH': '/tmp/pulse-runtime',  # Pulse audio runtime
                    'SDL_AUDIODRIVER': 'coreaudio'  # Force Core Audio
                }
                
                for var, value in additional_audio_env.items():
                    if not os.environ.get(var):
                        os.environ[var] = value
                        if self.debug_mode:
                            print(f"🔍 DEBUG: Set {var}={value}")
            except Exception as e:
                if self.debug_mode:
                    print(f"🔍 DEBUG: Could not set additional audio environment: {e}")
            
            # Small delay to let audio subsystem stabilize
            import time
            time.sleep(0.2)  # Increased delay for better stability
            
            if self.debug_mode:
                print("🔍 DEBUG: Audio session configuration completed")
            
        except Exception as e:
            if self.debug_mode:
                print(f"🔍 DEBUG: Audio session configuration warning: {e}")
    
    def setup_hotkey(self):
        """Setup global hotkey ⌥ Space for recording toggle"""
        try:
            # Try the modern pynput approach first
            def on_hotkey():
                self.toggle_recording(None)
            
            # Set up the global hotkey listener
            self.hotkey_listener = keyboard.GlobalHotKeys({
                '<alt>+<space>': on_hotkey  # ⌥ Space (alt is Option on Mac)
            })
            self.hotkey_listener.start()
            print("🔥 Global hotkey enabled: ⌥ Space to toggle recording")
            
        except Exception as e:
            print(f"⚠️ GlobalHotKeys failed: {e}")
            print("🔄 Trying alternative hotkey implementation...")
            
            # Fallback to manual listener with modifier detection
            try:
                self._setup_manual_hotkey()
            except Exception as e2:
                print(f"❌ Hotkey setup failed completely: {e2}")
                print("ℹ️ You can still use the menu bar to toggle recording")
                self.hotkey_listener = None
    
    def _setup_manual_hotkey(self):
        """Manual hotkey implementation for compatibility"""
        self.alt_pressed = False
        self.space_pressed = False
        
        def on_press(key):
            try:
                if key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
                    self.alt_pressed = True
                elif key == keyboard.Key.space:
                    if self.alt_pressed:  # ⌥ Space combination
                        self.toggle_recording(None)
                    self.space_pressed = True
            except AttributeError:
                pass
        
        def on_release(key):
            try:
                if key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
                    self.alt_pressed = False
                elif key == keyboard.Key.space:
                    self.space_pressed = False
            except AttributeError:
                pass
        
        self.hotkey_listener = keyboard.Listener(
            on_press=on_press,
            on_release=on_release
        )
        self.hotkey_listener.start()
        print("🔥 Global hotkey enabled: ⌥ Space to toggle recording (manual mode)")
    
    
    
    def load_model(self):
        def load():
            try:
                if not MLX_AVAILABLE:
                    print("❌ Cannot load model - MLX not available")
                    self.update_status("MLX unavailable")
                    return
                
                print("📥 Loading parakeet model...")
                self.update_status("Loading model...")
                
                self.model = from_pretrained("mlx-community/parakeet-tdt-0.6b-v2")
                
                print("✅ Model loaded successfully - Voice transcriber is ready!")
                self.update_status("Ready")
            except Exception as e:
                print(f"❌ Failed to load model: {e}")
                self.update_status(f"Model load failed")
        
        threading.Thread(target=load, daemon=True).start()
    
    def init_recorder(self):
        def on_timeout_stop(audio_file):
            """Handle automatic timeout stop"""
            print("⏰ Recording stopped automatically after 1 minute")
            if self.debug_mode:
                print(f"🔍 DEBUG: timeout audio_file = {audio_file}")
                print(f"🔍 DEBUG: file exists = {audio_file and os.path.exists(audio_file) if audio_file else False}")
                print(f"🔍 DEBUG: model ready = {self.model is not None}")
            
            # Process the final recording - use complete audio for best quality
            if audio_file and os.path.exists(audio_file):
                try:
                    if self.model and self.model != "UNAVAILABLE":
                        if self.debug_mode:
                            print("🔍 DEBUG: Starting timeout final transcription...")
                        result = self.model.transcribe(audio_file)
                        final_text = result.text.strip()
                        if self.debug_mode:
                            print(f"🔍 DEBUG: Timeout transcription result = '{final_text}'")
                        
                        if final_text:
                            # Replace any chunk-based transcription with final complete transcription
                            self.transcribed_text = final_text
                            char_count = len(final_text)
                            if self.debug_mode:
                                print(f"📝 Transcription complete ({char_count} chars): '{self.transcribed_text}'")
                            else:
                                print(f"📝 Transcription complete ({char_count} chars)")
                            
                            if self.auto_copy:
                                self.copy_to_clipboard()
                        else:
                            print("⚠️ Timeout final transcription was empty")
                            self.update_status("Transcription empty")
                    else:
                        print("❌ Model not available for timeout final transcription")
                        self.transcribed_text = "[TEST] Simulated transcription from timeout"
                        if self.auto_copy:
                            self.copy_to_clipboard()
                except Exception as e:
                    print(f"Timeout final transcription error: {e}")
                finally:
                    if not self.debug_mode:
                        try:
                            os.remove(audio_file)
                        except OSError:
                            pass
            else:
                print("❌ No audio file available for timeout final transcription")
            
            # Reset UI state
            self.is_recording = False
            self.record_menu_item.title = "🎤 Start (⌥ Space)"
            self.title = "🎤"
            
            # Auto-paste if enabled and we have transcribed text
            if self.debug_mode:
                print(f"🔍 DEBUG: About to check auto-paste - auto_paste={self.auto_paste}, transcribed_text='{self.transcribed_text}'")
            if self.auto_paste and self.transcribed_text:
                import time
                if self.debug_mode:
                    print("🔄 Starting auto-paste sequence...")
                print("🔄 Preparing auto-paste...")
                time.sleep(1.0)
                self.simulate_paste()
                print("📋 Auto-paste sequence completed!")
            else:
                if not self.auto_paste and self.debug_mode:
                    print("ℹ️ Auto-paste is disabled")
                if not self.transcribed_text and self.debug_mode:
                    print("ℹ️ No transcribed text to paste")
            
            print("✅ Recording complete - Ready for next recording!")
        
        try:
            self.recorder = AudioRecorder(
                debug_mode=self.debug_mode,
                max_recording_time=60.0,  # 1 minute timeout
                stop_callback=on_timeout_stop
            )
            print("✅ Audio recorder initialized successfully")
        except Exception as e:
            print(f"❌ Failed to initialize audio recorder: {e}")
            self.recorder = None
    
    def toggle_recording(self, sender):
        if MLX_AVAILABLE and not self.model:
            print("⏳ Model not ready - Please wait for the model to load.")
            self.update_status("Model still loading...")
            return
        
        if not self.recorder:
            print("❌ Audio recorder not available")
            self.update_status("Recorder error")
            return
        
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()
    
    def start_recording(self):
        if self.debug_mode:
            print("🔍 DEBUG: start_recording() called")
        self.is_recording = True
        # Clear previous transcription for new recording
        self.transcribed_text = ""
        if self.debug_mode:
            print(f"🔍 DEBUG: Cleared transcribed_text, now: '{self.transcribed_text}'")
        # Update menu text
        self.record_menu_item.title = "🎤 Stop (⌥ Space)"
        print("🎙️ Initializing recorder and starting countdown...")
        if self.debug_mode:
            print(f"🔍 DEBUG: Recorder object: {self.recorder}")
            print(f"🔍 DEBUG: Recorder max_recording_time: {self.recorder.max_recording_time if self.recorder else 'None'}")
        
        def countdown_and_start():
            import time
            
            # Define callbacks first
            def on_recording_ready():
                pass  # Icon already shows recording state
            
            def on_audio_chunk(temp_file):
                if self.debug_mode:
                    print(f"🔍 DEBUG: Audio chunk received: {temp_file}")
                    print("ℹ️ Skipping chunk transcription, will process complete audio at end")
                if temp_file and not self.debug_mode:
                    try:
                        os.remove(temp_file)
                    except OSError:
                        pass
            
            # Start the recorder first (it will buffer audio during countdown)
            if self.debug_mode:
                print("🔍 DEBUG: About to call recorder.start_recording()")
            try:
                result = self.recorder.start_recording(callback=on_audio_chunk, 
                                             ready_callback=on_recording_ready)
                if self.debug_mode:
                    print(f"🔍 DEBUG: recorder.start_recording() returned: {result}")
            except Exception as e:
                print(f"❌ Failed to start recording: {e}")
                return
            
            # Now do the countdown while recorder is warming up
            print("🎙️ Get ready! Recording starting in 1 second...")
            for i in range(1, 0, -1):
                self.title = f"{i}"
                print(f"⏰ Starting in {i}...")
                time.sleep(1)
            
            # Recording is now active and ready
            self.title = "🔴"  # Red dot for recording
            print("🎙️ Recording NOW - Speak! (Audio capture already started)")
            self.update_status("Recording...")
        
        # Start countdown in background thread
        threading.Thread(target=countdown_and_start, daemon=True).start()
    
    def stop_recording(self):
        self.is_recording = False
        # Update menu text
        self.record_menu_item.title = "🎤 Start (⌥ Space)"
        print("🛑 Stopping recording... Capturing final words for 1 second...")
        self.update_status("Processing audio...")
        
        def finish_stop():
            import time
            # Background countdown for the 1-second buffer (no visual countdown)
            self.title = "⏸️"  # Just show pause/processing icon
            time.sleep(1)  # Wait 1 second in background
            
            self.title = "🎤"  # Back to microphone
            
            def process_final():
                # Stop recording - we already waited 1 second, so give recorder a shorter delay
                final_file = self.recorder.stop_recording(final_delay=1.0)  # 1 second delay to capture final words
                if final_file and os.path.exists(final_file):
                    if self.debug_mode:
                        print(f"🔍 DEBUG: Processing final audio file: {final_file}")
                    # Transcribe the complete final recording for best quality
                    try:
                        if self.model and self.model != "UNAVAILABLE":
                            if self.debug_mode:
                                print("🔍 DEBUG: Starting final transcription...")
                            result = self.model.transcribe(final_file)
                            final_text = result.text.strip()
                            if self.debug_mode:
                                print(f"🔍 DEBUG: Final transcription result: '{final_text}'")
                            
                            if final_text:
                                # Replace chunk-based transcription with final high-quality transcription
                                self.transcribed_text = final_text
                                char_count = len(final_text)
                                if self.debug_mode:
                                    print(f"📝 Transcription complete ({char_count} chars): '{self.transcribed_text}'")
                                else:
                                    print(f"📝 Transcription complete ({char_count} chars)")
                                
                                if self.auto_copy:
                                    self.copy_to_clipboard()
                            else:
                                print("⚠️ Final transcription was empty")
                                self.update_status("Transcription empty")
                        else:
                            print("❌ Model not available for final transcription - using test text")
                            self.transcribed_text = "[TEST] This is simulated transcription text for testing"
                            if self.auto_copy:
                                self.copy_to_clipboard()
                    except Exception as e:
                        print(f"❌ Final transcription error: {e}")
                    finally:
                        # Clean up the file
                        if not self.debug_mode:
                            try:
                                os.remove(final_file)
                            except OSError:
                                pass
                
                print("✅ Recording complete - Ready for next recording!")
                
                # Reset status if no transcription occurred
                if not self.transcribed_text:
                    self.update_status("Ready")
                
                # Auto-paste if enabled and we have transcribed text
                if self.auto_paste and self.transcribed_text:
                    import time
                    print("🔄 Preparing auto-paste...")
                    time.sleep(1.0)  # Longer delay to ensure the app that should receive the paste is focused
                    self.simulate_paste()
                    print("📋 Auto-paste sequence completed!")
                else:
                    # If no auto-paste, still show final status
                    if self.transcribed_text and not self.auto_paste:
                        if self.debug_mode:
                            print("ℹ️ Auto-paste disabled - text available in clipboard")
            
            threading.Thread(target=process_final, daemon=True).start()
        
        threading.Thread(target=finish_stop, daemon=True).start()
    
    
    
    def copy_to_clipboard(self):
        if self.transcribed_text:
            try:
                pyperclip.copy(self.transcribed_text)
                char_count = len(self.transcribed_text)
                if self.debug_mode:
                    print(f"📋 Text copied to clipboard ({char_count} chars): '{self.transcribed_text}'")
                else:
                    print(f"📋 Text copied to clipboard ({char_count} chars)")
                
                # Update status to show transcription success
                self.update_status(f"Transcribed: {char_count} chars")
            except Exception as e:
                print(f"❌ Failed to copy to clipboard: {e}")
                self.update_status("Copy failed")
        else:
            if self.debug_mode:
                print("ℹ️ No transcribed text to copy.")
            self.update_status("No text to copy")
    
    
    
    def toggle_auto_copy(self, sender):
        self.auto_copy = not self.auto_copy
        self.auto_copy_menu.state = 1 if self.auto_copy else 0
        status = "enabled" if self.auto_copy else "disabled"
        print(f"📋 Auto-copy {status}")
    
    def toggle_auto_paste(self, sender):
        self.auto_paste = not self.auto_paste
        self.auto_paste_menu.state = 1 if self.auto_paste else 0
        status = "enabled" if self.auto_paste else "disabled"
        print(f"⌨️ Auto-paste {status}")
    
    def simulate_paste(self):
        """Simulate Cmd+V paste action"""
        try:
            if self.debug_mode:
                print(f"🔄 Attempting to simulate Cmd+V paste for text: '{self.transcribed_text[:50]}{'...' if len(self.transcribed_text) > 50 else ''}'")
            else:
                print("🔄 Attempting to simulate Cmd+V paste...")
            
            # Use pynput method directly (more reliable from app bundle)
            try:
                if self.debug_mode:
                    print("🔄 Using pynput method...")
                import time
                time.sleep(0.1)  # Small delay for reliability
                self.keyboard.press(Key.cmd)
                self.keyboard.press('v')
                self.keyboard.release('v')
                self.keyboard.release(Key.cmd)
                print("✅ Cmd+V simulation completed (pynput)")
                self.update_status("Auto-paste successful")
                return
            except Exception as e:
                print(f"⚠️ Pynput method failed: {e}")
            
            # Fallback to AppleScript if pynput fails
            import subprocess
            try:
                if self.debug_mode:
                    print("🔄 Trying AppleScript fallback...")
                applescript = '''
                tell application "System Events"
                    keystroke "v" using command down
                end tell
                '''
                result = subprocess.run(['osascript', '-e', applescript], 
                                      capture_output=True, text=True, timeout=3)
                if result.returncode == 0:
                    print("✅ Cmd+V simulation completed (AppleScript)")
                    self.update_status("Auto-paste successful")
                    return
                else:
                    print(f"⚠️ AppleScript failed: {result.stderr}")
            except Exception as e:
                print(f"⚠️ AppleScript method failed: {e}")
            
            # If both methods fail
            print("📋 Text copied to clipboard - please paste manually with Cmd+V")
            print("🔧 If auto-paste isn't working, try: System Settings > Privacy & Security > Accessibility > Add your terminal app")
            self.update_status("Auto-paste failed")
                
        except Exception as e:
            print(f"❌ Failed to simulate paste: {e}")
            print("📋 Text copied to clipboard - please paste manually with Cmd+V")
            self.update_status("Paste error")
    
    def toggle_debug_mode(self, sender):
        if self.is_recording:
            print("⚠️ Cannot change debug mode while recording.")
            return
        
        self.debug_mode = not self.debug_mode
        self.debug_mode_menu.state = 1 if self.debug_mode else 0
        
        # Set up or tear down file logging based on debug mode
        if self.debug_mode:
            self.setup_debug_logging()
            print("🐛 Debug mode enabled - logging to ~/Desktop/whispel_debug.log")
        else:
            self.teardown_debug_logging()
            print("🐛 Debug mode disabled - logging stopped")
        
        # Reinitialize recorder with new debug mode
        self.init_recorder()
        
        status = "enabled" if self.debug_mode else "disabled"
        print(f"🐛 Debug mode {status}")
    
    def open_accessibility_settings(self, sender):
        """Open macOS Accessibility settings"""
        try:
            import subprocess
            print("🔧 Opening System Settings > Privacy & Security > Accessibility...")
            subprocess.run(['open', 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'])
            print("📋 Instructions:")
            print("1. Click the '+' button")
            print("2. Navigate to Applications and select Whispel")
            print("3. Check the box next to Whispel")
            print("4. Restart Whispel for auto-paste to work")
        except Exception as e:
            print(f"❌ Failed to open settings: {e}")
            print("🔧 Please manually open: System Settings > Privacy & Security > Accessibility")
    
    def cleanup_on_exit(self):
        """Clean up resources when app exits"""
        if self.debug_log_file:
            self.teardown_debug_logging()
    


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Voice Transcriber - Menu Bar Speech-to-Text App')
    parser.add_argument('--debug-info', action='store_true', 
                       help='Show debug directory information')
    
    args = parser.parse_args()
    
    if args.debug_info:
        # Show debug info and exit
        import tempfile
        from audio_recorder import AudioRecorder
        recorder = AudioRecorder(debug_mode=True)
        debug_dir = recorder.get_debug_directory()
        if debug_dir:
            print(f"🗂️ Debug directory: {debug_dir}")
        else:
            print("🗂️ Debug directory not yet created. Enable debug mode and record something first.")
        exit(0)
    
    app = VoiceTranscriber()
    try:
        app.run()
    finally:
        app.cleanup_on_exit()