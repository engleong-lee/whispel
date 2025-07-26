import pyaudio
import wave
import threading
import time
import os
import tempfile
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
        self.audio_data = []
        self.frames = []
        self.recording_thread = None
        self.stream = None
        self.start_time = 0
        self.audio = None
        self.chunk_counter = 0
        self._lock = threading.Lock()
        self._initialize_audio()
        
        if self.debug_mode:
            self._setup_debug_directory()
    
    def _initialize_audio(self):
        """Initialize PyAudio instance if not already initialized."""
        if self.audio is None:
            try:
                self.audio = pyaudio.PyAudio()
                return True
            except Exception as e:
                print(f"Failed to initialize PyAudio: {str(e)}")
                self.audio = None
                return False
        return True
        
    def _setup_debug_directory(self):
        self.debug_dir = os.path.join(os.path.dirname(__file__), "debug_audio")
        if not os.path.exists(self.debug_dir):
            os.makedirs(self.debug_dir)
        
    def start_recording(self, callback: Optional[Callable[[str], None]] = None, 
                       chunk_duration: float = 5.0, ready_callback: Optional[Callable[[], None]] = None,
                       use_stream_callback: bool = True):
        with self._lock:
            if self.is_recording or not self._initialize_audio():
                return False
            
            self.is_recording = True
            self.audio_data = []
            self.frames = []
            self.chunk_counter = 0
            self.start_time = time.time()
        
        if use_stream_callback:
            return self._start_with_stream_callback(callback, ready_callback)
        else:
            return self._start_with_manual_threading(callback, chunk_duration, ready_callback)
    
    def _start_with_stream_callback(self, callback: Optional[Callable[[str], None]] = None,
                                   ready_callback: Optional[Callable[[], None]] = None):
        """Start recording using PyAudio's stream callback (recommended approach)."""
        try:
            # Store the callback for chunk processing if provided
            self.chunk_callback = callback
            self.chunk_frames_target = int(self.sample_rate * 3.0)  # Default 3 second chunks
            self.current_chunk_frames = 0
            self.current_chunk_data = []
            
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                stream_callback=self._audio_callback_with_chunks
            )
            
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
    
    def _start_with_manual_threading(self, callback: Optional[Callable[[str], None]] = None,
                                    chunk_duration: float = 5.0, 
                                    ready_callback: Optional[Callable[[], None]] = None):
        """Legacy manual threading approach for backward compatibility."""
        def record():
            try:
                stream = self.audio.open(
                    format=self.format,
                    channels=self.channels,
                    rate=self.sample_rate,
                    input=True,
                    frames_per_buffer=self.chunk_size
                )
                
                # Allow audio system to stabilize before signaling ready
                time.sleep(1.0)
                
                # Signal that recording is actually ready
                if ready_callback:
                    ready_callback()
                
                chunk_frames = int(self.sample_rate * chunk_duration)
                frames_collected = 0
                current_chunk = []
                
                while self.is_recording:
                    data = stream.read(self.chunk_size, exception_on_overflow=False)
                    current_chunk.append(data)
                    self.audio_data.append(data)  # Accumulate all audio data
                    frames_collected += self.chunk_size
                    
                    if frames_collected >= chunk_frames:
                        if callback:
                            temp_file = self._save_chunk_to_temp_file(current_chunk)
                            callback(temp_file)
                        
                        current_chunk = []
                        frames_collected = 0
                
                if current_chunk and callback:
                    temp_file = self._save_chunk_to_temp_file(current_chunk)
                    callback(temp_file)
                    
                stream.stop_stream()
                stream.close()
                
            except Exception as e:
                print(f"Recording error: {e}")
                with self._lock:
                    self.is_recording = False
        
        self.recording_thread = threading.Thread(target=record)
        self.recording_thread.start()
        return True
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Audio stream callback to collect frames."""
        with self._lock:
            if self.is_recording:
                self.frames.append(in_data)
                self.audio_data.append(in_data)
        return (in_data, pyaudio.paContinue)
    
    def _audio_callback_with_chunks(self, in_data, frame_count, time_info, status):
        """Audio stream callback that also processes chunks for real-time transcription."""
        with self._lock:
            if self.is_recording:
                self.frames.append(in_data)
                self.audio_data.append(in_data)
                
                # Handle chunk processing if callback is provided
                if hasattr(self, 'chunk_callback') and self.chunk_callback:
                    self.current_chunk_data.append(in_data)
                    self.current_chunk_frames += frame_count
                    
                    # Check if we've collected enough frames for a chunk
                    if self.current_chunk_frames >= self.chunk_frames_target:
                        # Process the chunk in a separate thread to avoid blocking audio
                        import threading
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
        
        # Add delay to capture final words for manual threading mode
        if final_delay > 0 and self.recording_thread is not None:
            time.sleep(final_delay)
        
        try:
            # Clean up stream and thread resources
            self._cleanup()
            
            if self.recording_thread:
                self.recording_thread.join()
            
            # Check recording duration and save
            audio_data = self.frames if self.frames else self.audio_data
            if audio_data:
                duration = (len(audio_data) * self.chunk_size) / self.sample_rate
                if duration < 1.0:
                    raise ValueError("Recording must be at least 1 second long")
                
                return self._save_to_temp_file(audio_data)
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
            
            return temp_filename
    
    def _save_to_file(self, filename: str = "recorded_audio.wav") -> str:
        """Legacy file saving method for backward compatibility."""
        if self.debug_mode:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"final_{timestamp}.wav"
            filepath = os.path.join(self.debug_dir, filename)
        else:
            filepath = os.path.join(os.path.dirname(__file__), filename)
        
        audio_data = self.frames if self.frames else self.audio_data
        with wave.open(filepath, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.audio.get_sample_size(self.format))
            wf.setframerate(self.sample_rate)
            wf.writeframes(b''.join(audio_data))
        
        return filepath
    
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