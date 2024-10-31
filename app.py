from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import subprocess
import os
import tempfile
import threading
import queue
import signal
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
# Enable CORS for security
CORS(app, resources={r"/*": {"origins": os.getenv('ALLOWED_ORIGINS', '*')}})

# Add configuration class
class Config:
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 5000))
    TIMEOUT = int(os.getenv('CODE_TIMEOUT', 10))
    MAX_CONTENT_LENGTH = 16 * 1024  # 16KB max-limit for code submission

class CodeExecutor:
    def __init__(self, timeout=5):
        self.timeout = timeout

    def run_code_with_timeout(self, code, input_value):
        result_queue = queue.Queue()
        thread = threading.Thread(
            target=self._run_code,
            args=(code, input_value, result_queue)
        )
        thread.start()
        thread.join(timeout=self.timeout)
        
        if thread.is_alive():
            thread.join()  # Ensure thread cleanup
            return None, "Timeout: Code execution took too long"
            
        try:
            stdout, stderr = result_queue.get_nowait()
            return stdout, stderr
        except queue.Empty:
            return None, "Execution failed"

    def _run_code(self, code, input_value, result_queue):
        try:
            # Modify the code to inject the input value
            modified_code = f"""
input_value = {repr(input_value)}  # System provided input
{code}
"""
            # Create a temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(modified_code.replace('\r\n', '\n'))
                temp_filename = f.name

            # Run the code
            process = subprocess.Popen(
                ['python', temp_filename],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate(timeout=self.timeout)
            
            # Clean output and handle errors
            stdout = stdout.strip()
            stderr = stderr.strip()
            
            result_queue.put((stdout, stderr))
            
        except subprocess.TimeoutExpired:
            process.kill()
            result_queue.put((None, "Timeout: Code execution took too long"))
        except Exception as e:
            result_queue.put((None, str(e)))
        finally:
            try:
                os.unlink(temp_filename)
            except:
                pass

@app.route('/')
def index():
    return send_from_directory(os.getcwd(), 'index.html')

@app.route('/run', methods=['POST'])
def run_code():
    try:
        data = request.get_json()
        code = data['code']
        test_cases = data['testCases']
        output = []

        executor = CodeExecutor(timeout=Config.TIMEOUT)

        for test_case in test_cases:
            input_value = test_case['input']
            stdout, stderr = executor.run_code_with_timeout(code, input_value)
            
            if stderr:
                output.append(f"Error: {stderr}")
            else:
                result = stdout.strip() if stdout is not None else "Timeout"
                output.append(result)

        return jsonify({'output': output})
    
    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG
    )
