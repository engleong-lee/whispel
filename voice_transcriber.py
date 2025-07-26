import rumps
import threading
import os
import pyperclip
from parakeet_mlx import from_pretrained
from audio_recorder import AudioRecorder
from pynput.keyboard import Key, Controller
from pynput import keyboard


class VoiceTranscriber(rumps.App):
    def __init__(self):
        super(VoiceTranscriber, self).__init__("🎤")
        self.title = "🎤"  # Just the icon
        
        self.model = None
        self.recorder = None  
        self.is_recording = False
        self.transcribed_text = ""
        self.debug_mode = False
        self.auto_copy = True
        self.auto_paste = True  # Auto-paste after recording
        self.keyboard = Controller()  # For simulating key presses
        
        self.setup_menu()
        self.setup_hotkey()
        
        self.init_recorder()
        self.load_model()
    
    def setup_menu(self):
        # Create menu items with essential options
        self.record_menu_item = rumps.MenuItem("🎤 Start (Option+Space)", callback=self.toggle_recording)
        self.auto_copy_menu = rumps.MenuItem("Auto-copy to clipboard", callback=self.toggle_auto_copy)
        self.auto_paste_menu = rumps.MenuItem("Auto-paste after recording", callback=self.toggle_auto_paste)
        self.debug_mode_menu = rumps.MenuItem("Debug mode", callback=self.toggle_debug_mode)
        
        # Set initial menu state
        self.auto_copy_menu.state = 1 if self.auto_copy else 0
        self.auto_paste_menu.state = 1 if self.auto_paste else 0
        self.debug_mode_menu.state = 0  # Debug mode starts off
        
        self.menu = [
            self.record_menu_item,
            None,  # separator
            self.auto_copy_menu,
            self.auto_paste_menu,
            self.debug_mode_menu
        ]
    
    def setup_hotkey(self):
        """Setup global hotkey Option+Space for recording toggle"""
        try:
            # Try the modern pynput approach first
            def on_hotkey():
                self.toggle_recording(None)
            
            # Set up the global hotkey listener
            self.hotkey_listener = keyboard.GlobalHotKeys({
                '<alt>+<space>': on_hotkey  # Option+Space (alt is Option on Mac)
            })
            self.hotkey_listener.start()
            print("🔥 Global hotkey enabled: Option+Space to toggle recording")
            
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
                    if self.alt_pressed:  # Option+Space combination
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
        print("🔥 Global hotkey enabled: Option+Space to toggle recording (manual mode)")
    
    
    
    def load_model(self):
        def load():
            try:
                self.model = from_pretrained("mlx-community/parakeet-tdt-0.6b-v2")
                print("✅ Model loaded successfully - Voice transcriber is ready!")
            except Exception as e:
                print(f"❌ Failed to load model: {e}")
        
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
                    if self.model:
                        if self.debug_mode:
                            print("🔍 DEBUG: Starting timeout final transcription...")
                        result = self.model.transcribe(audio_file)
                        final_text = result.text.strip()
                        if self.debug_mode:
                            print(f"🔍 DEBUG: Timeout transcription result = '{final_text}'")
                        
                        if final_text:
                            # Replace any chunk-based transcription with final complete transcription
                            self.transcribed_text = final_text
                            print(f"📝 Transcription complete: '{self.transcribed_text}'")
                            
                            if self.auto_copy:
                                self.copy_to_clipboard()
                        else:
                            print("⚠️ Timeout final transcription was empty")
                    else:
                        print("❌ Model not available for timeout final transcription")
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
            self.record_menu_item.title = "🎤 Start (Option+Space)"
            self.title = "🎤"
            
            # Auto-paste if enabled and we have transcribed text
            if self.debug_mode:
                print(f"🔍 DEBUG: About to check auto-paste - auto_paste={self.auto_paste}, transcribed_text='{self.transcribed_text}'")
            if self.auto_paste and self.transcribed_text:
                import time
                if self.debug_mode:
                    print("🔄 Starting auto-paste sequence...")
                time.sleep(0.5)
                self.simulate_paste()
                print("📋 Auto-pasted transcribed text!")
            else:
                if not self.auto_paste and self.debug_mode:
                    print("ℹ️ Auto-paste is disabled")
                if not self.transcribed_text and self.debug_mode:
                    print("ℹ️ No transcribed text to paste")
            
            print("✅ Recording complete - Ready for next recording!")
        
        self.recorder = AudioRecorder(
            debug_mode=self.debug_mode,
            max_recording_time=60.0,  # 1 minute timeout
            stop_callback=on_timeout_stop
        )
    
    def toggle_recording(self, sender):
        if not self.model:
            print("⏳ Model not ready - Please wait for the model to load.")
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
        self.record_menu_item.title = "🎤 Stop (Option+Space)"
        print("🎙️ Initializing recorder and starting countdown...")
        if self.debug_mode:
            print(f"🔍 DEBUG: Recorder object: {self.recorder}")
            print(f"🔍 DEBUG: Recorder max_recording_time: {self.recorder.max_recording_time}")
        
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
            result = self.recorder.start_recording(callback=on_audio_chunk, chunk_duration=3.0, 
                                         ready_callback=on_recording_ready, use_stream_callback=True)
            if self.debug_mode:
                print(f"🔍 DEBUG: recorder.start_recording() returned: {result}")
            
            # Now do the countdown while recorder is warming up
            print("🎙️ Get ready! Recording starting in 1 second...")
            for i in range(1, 0, -1):
                self.title = f"{i}"
                print(f"⏰ Starting in {i}...")
                time.sleep(1)
            
            # Recording is now active and ready
            self.title = "🔴"  # Red dot for recording
            print("🎙️ Recording NOW - Speak! (Audio capture already started)")
        
        # Start countdown in background thread
        threading.Thread(target=countdown_and_start, daemon=True).start()
    
    def stop_recording(self):
        self.is_recording = False
        # Update menu text
        self.record_menu_item.title = "🎤 Start (Option+Space)"
        print("🛑 Stopping recording... Capturing final words for 1 second...")
        
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
                        if self.model:
                            if self.debug_mode:
                                print("🔍 DEBUG: Starting final transcription...")
                            result = self.model.transcribe(final_file)
                            final_text = result.text.strip()
                            if self.debug_mode:
                                print(f"🔍 DEBUG: Final transcription result: '{final_text}'")
                            
                            if final_text:
                                # Replace chunk-based transcription with final high-quality transcription
                                self.transcribed_text = final_text
                                print(f"📝 Transcription complete: '{self.transcribed_text}'")
                                
                                if self.auto_copy:
                                    self.copy_to_clipboard()
                            else:
                                print("⚠️ Final transcription was empty")
                        else:
                            print("❌ Model not available for final transcription")
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
                
                # Auto-paste if enabled and we have transcribed text
                if self.auto_paste and self.transcribed_text:
                    import time
                    time.sleep(0.5)  # Small delay to ensure the app that should receive the paste is focused
                    self.simulate_paste()
                    print("📋 Auto-pasted transcribed text!")
            
            threading.Thread(target=process_final, daemon=True).start()
        
        threading.Thread(target=finish_stop, daemon=True).start()
    
    def add_transcribed_text(self, text):
        # Clean up the text by removing filler words from the end
        cleaned_text = self.clean_transcript_end(text)
        
        # Only add non-empty text
        if cleaned_text:
            if self.transcribed_text:
                self.transcribed_text += " " + cleaned_text
            else:
                self.transcribed_text = cleaned_text
            if self.debug_mode:
                print(f"📝 Added transcribed text: '{cleaned_text}'")
                print(f"📝 Total transcribed text now: '{self.transcribed_text}'")
        else:
            if self.debug_mode:
                print(f"⚠️ Cleaned text was empty from: '{text}'")
    
    def clean_transcript_end(self, text):
        """Remove filler words from the end of transcript"""
        if not text:
            return text
            
        # List of filler words to remove from the end
        filler_words = ["uh", "um", "hmm", "ah", "er", "eh", "yeah", "mm", "mm-hmm", 
                       "uh-huh", "mm-mm", "uh-oh", "ah-ha", "mm-kay", "uh-uh"]
        
        # Split into words and work backwards
        words = text.strip().split()
        if not words:
            return text
            
        # Remove filler words from the end
        while words and words[-1].lower().rstrip('.,!?;:') in filler_words:
            words.pop()
        
        # Rejoin the cleaned words
        cleaned = " ".join(words)
        return cleaned if cleaned else ""  # Return empty string if everything was removed (like single "uh")
    
    def copy_to_clipboard(self):
        if self.transcribed_text:
            try:
                pyperclip.copy(self.transcribed_text)
                if self.debug_mode:
                    print(f"📋 Text copied to clipboard: '{self.transcribed_text}'")
                else:
                    print("📋 Text copied to clipboard!")
            except Exception as e:
                print(f"❌ Failed to copy to clipboard: {e}")
        else:
            if self.debug_mode:
                print("ℹ️ No transcribed text to copy.")
    
    def clear_text(self, sender):
        self.transcribed_text = ""
        print("🗑️ Transcribed text cleared.")
    
    def show_text(self, sender):
        if self.transcribed_text:
            # Create a temporary file to display the text
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(self.transcribed_text)
                temp_path = f.name
            
            # Open the file with default text editor
            os.system(f'open "{temp_path}"')
            print(f"📄 Opened transcribed text in default editor: {temp_path}")
        else:
            print("ℹ️ No transcribed text to display.")
    
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
                print("🔄 Attempting to simulate Cmd+V paste...")
            # Press Cmd+V
            self.keyboard.press(Key.cmd)
            self.keyboard.press('v')
            self.keyboard.release('v')
            self.keyboard.release(Key.cmd)
            if self.debug_mode:
                print("✅ Cmd+V simulation completed")
        except Exception as e:
            print(f"❌ Failed to simulate paste: {e}")
    
    def toggle_debug_mode(self, sender):
        if self.is_recording:
            print("⚠️ Cannot change debug mode while recording.")
            return
        
        self.debug_mode = not self.debug_mode
        self.debug_mode_menu.state = 1 if self.debug_mode else 0
        self.init_recorder()
        status = "enabled" if self.debug_mode else "disabled"
        print(f"🐛 Debug mode {status}")
    
    def show_debug_info(self, sender):
        if self.debug_mode and self.recorder:
            debug_dir = self.recorder.get_debug_directory()
            if debug_dir:
                print(f"🗂️ Audio files saved to: {debug_dir}")
            else:
                print("🗂️ Debug directory not yet created.")
        else:
            print("ℹ️ Debug mode is disabled. Audio files will be deleted after transcription.")


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
    app.run()