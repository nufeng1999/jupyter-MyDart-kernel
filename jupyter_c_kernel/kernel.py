from queue import Queue, Empty
from threading import Thread

from ipykernel.kernelbase import Kernel
import subprocess
import tempfile
import os
import os.path as path

class JupyterSubprocess(subprocess.Popen):
    def __init__(self, cmd, write_to_stdout, write_to_stderr):
        self._write_to_stdout = write_to_stdout
        self._write_to_stderr = write_to_stderr

        super().__init__(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)

        self._stdout_queue = Queue()
        self._stdout_thread = Thread(target=JupyterSubprocess._enqueue_output, args=(self.stdout, self._stdout_queue))
        self._stdout_thread.daemon = True
        self._stdout_thread.start()

        self._stderr_queue = Queue()
        self._stderr_thread = Thread(target=JupyterSubprocess._enqueue_output, args=(self.stderr, self._stderr_queue))
        self._stderr_thread.daemon = True
        self._stderr_thread.start()

    @staticmethod
    def _enqueue_output(contents, queue):
        for line in iter(lambda: contents.read(4096), b''):
            queue.put(line)
        contents.close()

    def write_contents(self):
        try:
            stdout_contents = self._stdout_queue.get_nowait()
        except Empty:
            pass
        else:
            self._write_to_stdout(stdout_contents)
        try:
            stderr_contents = self._stderr_queue.get_nowait()
        except Empty:
            pass
        else:
            self._write_to_stderr(stderr_contents)


class CKernel(Kernel):
    implementation = 'jupyter_c_kernel'
    implementation_version = '1.0'
    language = 'c'
    language_version = 'C11'
    language_info = {'name': 'c',
                     'mimetype': 'text/plain',
                     'file_extension': 'c'}
    banner = "C kernel.\n" \
             "Uses gcc, compiles in C11, and creates source code files and executables in temporary folder.\n"

    def __init__(self, *args, **kwargs):
        super(CKernel, self).__init__(*args, **kwargs)
        self.files = []
        mastertemp = tempfile.mkstemp(suffix='.out')
        os.close(mastertemp[0])
        self.master_path = mastertemp[1]
        filepath = path.join(path.dirname(path.realpath(__file__)), '..', 'resources', 'master.c')
        subprocess.call(['gcc', filepath, '-std=c11', '-rdynamic', '-ldl', '-o', self.master_path])

    def cleanup_files(self):
        """Remove all the temporary files created by the kernel"""
        for file in self.files:
            os.remove(file)
        os.remove(self.master_path)

    def new_temp_file(self, **kwargs):
        """Create a new temp file to be deleted when the kernel shuts down"""
        # We don't want the file to be deleted when closed, but only when the kernel stops
        kwargs['delete'] = False
        kwargs['mode'] = 'w'
        file = tempfile.NamedTemporaryFile(**kwargs)
        self.files.append(file.name)
        return file

    def _write_to_stdout(self, contents):
        self.send_response(self.iopub_socket, 'stream', {'name': 'stdout', 'text': contents})

    def _write_to_stderr(self, contents):
        self.send_response(self.iopub_socket, 'stream', {'name': 'stderr', 'text': contents})

    def create_jupyter_subprocess(self, cmd):
        return JupyterSubprocess(cmd,
                                 lambda contents: self._write_to_stdout(contents.decode()),
                                 lambda contents: self._write_to_stderr(contents.decode()))

    def compile_with_gcc(self, source_filename, binary_filename):
        args = ['gcc', source_filename, '-std=c11', '-fPIC', '-shared', '-rdynamic', '-o', binary_filename]
        return self.create_jupyter_subprocess(args)

    def do_execute(self, code, silent, store_history=True,
                   user_expressions=None, allow_stdin=False):
        with self.new_temp_file(suffix='.c') as source_file:
            source_file.write(code)
            source_file.flush()
            with self.new_temp_file(suffix='.out') as binary_file:
                p = self.compile_with_gcc(source_file.name, binary_file.name)
                while p.poll() is None:
                    p.write_contents()
                p.write_contents()
                if p.returncode != 0:  # Compilation failed
                    self._write_to_stderr(
                            "[C kernel] GCC exited with code {}, the executable will not be executed".format(
                                    p.returncode))
                    return {'status': 'ok', 'execution_count': self.execution_count, 'payload': [],
                            'user_expressions': {}}

        p = self.create_jupyter_subprocess([self.master_path, binary_file.name])
        while p.poll() is None:
            p.write_contents()
        p.write_contents()

        if p.returncode != 0:
            self._write_to_stderr("[C kernel] Executable exited with code {}".format(p.returncode))
        return {'status': 'ok', 'execution_count': self.execution_count, 'payload': [], 'user_expressions': {}}

    def do_shutdown(self, restart):
        """Cleanup the created source code files and executables when shutting down the kernel"""
        self.cleanup_files()
