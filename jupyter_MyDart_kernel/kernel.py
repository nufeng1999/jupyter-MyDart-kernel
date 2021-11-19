from queue import Queue
from threading import Thread

from ipykernel.kernelbase import Kernel
from pexpect import replwrap, EOF
from multiprocessing import Process, Pipe
import pexpect
import re
import subprocess
import tempfile
import os
import os.path as path
import signal
import pty
import sys
import time

usleep = lambda x: time.sleep(x/1000000.0)

g_sysstdout=sys.stdout
g_sysstderr=sys.stderr
g_sysstdin=sys.stdin
class IREPLWrapper(replwrap.REPLWrapper):
    """A subclass of REPLWrapper that gives incremental output
    specifically for gdb_kernel.

    The parameters are the same as for REPLWrapper, except for one
    extra parameter:

    :param line_output_callback: a callback method to receive each batch
      of incremental output. It takes one string parameter.
    """
    def __init__(self, write_to_stdout, write_to_stderr, read_from_stdin,
                cmd_or_spawn,replsetip, orig_prompt, prompt_change,
                extra_init_cmd=None, line_output_callback=None):
        self._write_to_stdout = write_to_stdout
        self._write_to_stderr = write_to_stderr
        self._read_from_stdin = read_from_stdin
        self.line_output_callback = line_output_callback
        self.replsetip=replsetip
        self.startflag=True
        self.startexpecttimeout=60
        # x = time.localtime(time.time())
        self.start_time = time.time()
        replwrap.REPLWrapper.__init__(self, cmd_or_spawn, orig_prompt,
                                      prompt_change,extra_init_cmd=extra_init_cmd)
 
    def _expect_prompt(self, timeout=-1):
        if timeout == None:
            # "None" means we are executing code from a Jupyter cell by way of the run_command
            # in the do_execute() code below, so do incremental output.
            # self.line_output_callback("\n find "+self.prompt+"\n")
            retry=0
            received=False
            cmdstart_time = time.time()
            cmdexectimeout=10
            while True:
                if self.startflag :
                    cmdexectimeout=None
                    # y = time.localtime(time.time())
                    # now_time = time.strftime('%S', y)
                    run_time = time.time() - self.start_time
                    if run_time > self.startexpecttimeout:
                        self.startflag=False
                        self.line_output_callback(self.child.before + '\r\n')
                        self.line_output_callback("\n0End of startup process\n")
                        break
                try:
                    pos = self.child.expect_exact(['\r\n', self.continuation_prompt, self.replsetip, pexpect.EOF, pexpect.TIMEOUT],timeout=cmdexectimeout)
                    # pos = self.child.expect_exact(['\r\n', self.continuation_prompt,self.prompt,u'\r\n'],timeout=10)
                    # self.line_output_callback("\nexpect_exact process :"+ str(pos) +"\n")
                    if pos == 2:
                        # End of line received
                        self.line_output_callback(self.child.before +self.replsetip+ '\r\n')
                        self.line_output_callback("\n1End of startup process\n")
                        self.replsetip='\r\n'#pexpect.EOF
                        cmdexectimeout=10
                        self.startflag=False
                        break
                    elif pos == 0 or pos ==3 or pos ==4:
                        # End of line received
                        if len(self.child.before) != 0:
                            self.line_output_callback(self.child.before + '\r\n')
                            if not received and not self.startflag:
                                cmdstart_time = time.time()
                                received=True
                            
                        if self.startflag:
                            continue
                        run_time = time.time() - cmdstart_time
                        if run_time > 10:
                            # self.line_output_callback("\nexpect_exact exit :"+ str(retry) +"\n")
                            break
                        # retry=retry+1
                        # self.line_output_callback("\nexpect_exact retry :"+ str(retry) +"\n")
                    else:
                        self.line_output_callback("\nexpect_exact else \n")
                        if len(self.child.before) != 0:
                            # prompt received, but partial line precedes it
                            self.line_output_callback(self.child.before)
                        # if not self.startflag :
                        else:
                            if self.startflag :
                                continue
                            self.line_output_callback("\nexpect_exact break2 :"+ str(pos) +"\n")
                            break
                except Exception as e:
                    # self.line_output_callback(self.child.before)
                    self._write_to_stderr("[Dart kernel] Error:Executable _expect_prompt error! "+str(e)+"\n")
        else:
            # Otherwise, use existing non-incremental code
            pos = replwrap.REPLWrapper._expect_prompt(self, timeout=timeout)
        # Prompt received, so return normally
        return pos


class RealTimeSubprocess(subprocess.Popen):
    """
    A subprocess that allows to read its stdout and stderr in real time
    """

    inputRequest ="<inputRequest>"

    def __init__(self, cmd, write_to_stdout, write_to_stderr, read_from_stdin,cwd=None,shell=False,env=None):
        """
        :param cmd: the command to execute
        :param write_to_stdout: a callable that will be called with chunks of data from stdout
        :param write_to_stderr: a callable that will be called with chunks of data from stderr
        """
        self._write_to_stdout = write_to_stdout
        self._write_to_stderr = write_to_stderr
        self._read_from_stdin = read_from_stdin

        super().__init__(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE, bufsize=0,cwd=cwd,shell=shell,env=env)

        self._stdout_queue = Queue()
        self._stdout_thread = Thread(target=RealTimeSubprocess._enqueue_output, args=(self.stdout, self._stdout_queue))
        self._stdout_thread.daemon = True
        self._stdout_thread.start()

        self._stderr_queue = Queue()
        self._stderr_thread = Thread(target=RealTimeSubprocess._enqueue_output, args=(self.stderr, self._stderr_queue))
        self._stderr_thread.daemon = True
        self._stderr_thread.start()

    @staticmethod
    def _enqueue_output(stream, queue):
        """
        Add chunks of data from a stream to a queue until the stream is empty.
        """
        for line in iter(lambda: stream.read(4096), b''):
            queue.put(line)
        stream.close()

    def write_contents(self,magics=None):
        """
        Write the available content from stdin and stderr where specified when the instance was created
        :return:
        """

        def read_all_from_queue(queue):
            res = b''
            size = queue.qsize()
            while size != 0:
                res += queue.get_nowait()
                size -= 1
            return res

        stderr_contents = read_all_from_queue(self._stderr_queue)
        if stderr_contents:
            self._write_to_stderr(stderr_contents.decode())

        stdout_contents = read_all_from_queue(self._stdout_queue)
        if stdout_contents:
            contents = stdout_contents.decode()
            # if there is input request, make output and then
            # ask frontend for input
            start = contents.find(self.__class__.inputRequest)
            if(start >= 0):
                contents = contents.replace(self.__class__.inputRequest, '')
                if(len(contents) > 0):
                    self._write_to_stdout(contents,magics)
                readLine = ""
                while(len(readLine) == 0):
                    readLine = self._read_from_stdin()
                # need to add newline since it is not captured by frontend
                readLine += "\n"
                self.stdin.write(readLine.encode())
            else:
                self._write_to_stdout(contents,magics)


class DartKernel(Kernel):
    implementation = 'jupyter_MyDart_kernel'
    implementation_version = '1.0'
    language = 'Dart'
    language_version = '2.X.X'
    language_info = {'name': 'text/x-csrc',
                     'mimetype': 'text/x-csrc',
                     'file_extension': '.dart'}
    banner = "Dart kernel.\n" \
             "Uses Dart, compiles in dart, and creates source code files and executables in temporary folder.\n"

    main_head = "\n" \
            "\n" \
            "int main(List<String> arguments){\n"

    main_foot = "\nreturn 0;\n}"

    g_rtsps={}
    g_chkreplexit=True
    def __init__(self, *args, **kwargs):
        super(DartKernel, self).__init__(*args, **kwargs)
        self._allow_stdin = True
        self.readOnlyFileSystem = False
        self.bufferedOutput = True
        self.linkMaths = True # always link math library
        self.wAll = True # show all warnings by default
        self.wError = False # but keep comipiling for warnings
        self.files = []
        mastertemp = tempfile.mkstemp(suffix='.out')
        os.close(mastertemp[0])
        self.master_path = mastertemp[1]
        self.resDir = path.join(path.dirname(path.realpath(__file__)), 'resources')
        filepath = path.join(self.resDir, 'master.c')
        # subprocess.call(['gcc', filepath, '-std=c11', '-rdynamic', '-ldl', '-o', self.master_path])

        self.chk_replexit_thread = Thread(target=DartKernel.chk_replexit, args=(self.g_rtsps))
        self.chk_replexit_thread.daemon = True
        # self.chk_replexit_thread.start()

    def chk_replexit(grtsps): 
        while DartKernel.g_chkreplexit:
            try:
                if len(grtsps)>0: 
                    for key in grtsps:
                        if grtsps[key].child.terminated:
                            pass
                            # grtsps[key]._stdout_thread.join()
                            # grtsps[key]._stderr_thread.join()
                            # del grtsps[key]
                        else:
                            grtsps[key].write_contents()
            finally:
                pass
        if not DartKernel.g_chkreplexit:
            if len(grtsps)>0: 
                    for key in grtsps:
                        if grtsps[key].child.terminated:
                            pass
                            # grtsps[key]._stdout_thread.join()
                            # grtsps[key]._stderr_thread.join()
                            # del grtsps[key]
                        else:
                            grtsps[key].child.terminate(force=True)
    def cleanup_files(self):
        """Remove all the temporary files created by the kernel"""
        # keep the list of files create in case there is an exception
        # before they can be deleted as usual
        for file in self.files:
            if(os.path.exists(file)):
                os.remove(file)
        if(os.path.exists(self.master_path)):
            os.remove(self.master_path)

    def new_temp_file(self, **kwargs):
        """Create a new temp file to be deleted when the kernel shuts down"""
        # We don't want the file to be deleted when closed, but only when the kernel stops
        kwargs['delete'] = False
        kwargs['mode'] = 'w'
        file = tempfile.NamedTemporaryFile(**kwargs)
        self.files.append(file.name)
        return file

    def _write_display_data(self,mimetype='text/html',contents=""):

        self.send_response(self.iopub_socket, 'display_data', {'data': {mimetype:contents}, 'metadata': {mimetype:{}}})

    def _write_to_stdout(self,contents,magics=None):
        if magics !=None and len(magics['outputtype'])>0:
            self._write_display_data(mimetype=magics['outputtype'],contents=contents)
        else:
            self.send_response(self.iopub_socket, 'stream', {'name': 'stdout', 'text': contents})

    def _write_to_stderr(self, contents):
        self.send_response(self.iopub_socket, 'stream', {'name': 'stderr', 'text': contents})

    def _read_from_stdin(self):
        return self.raw_input()

    def readcodefile(self,filename,spacecount=0):
        filecode=''
        codelist1=None
        if not os.path.exists(filename):
            return ''
        with open(os.path.join(os.path.abspath(''),filename), 'r') as codef1:
            codelist1 = codef1.readlines()
        if len(codelist1)>0:
            for t in codelist1:
                filecode+=' '*spacecount + t
        return filecode
    #####################################################################
    def _start_replprg(self,command,args,magics):
        # Signal handlers are inherited by forked processes, and we can't easily
        # reset it from the subprocess. Since kernelapp ignores SIGINT except in
        # message handlers, we need to temporarily reset the SIGINT handler here
        # so that bash and its children are interruptible.
        sig = signal.signal(signal.SIGINT, signal.SIG_DFL)
        self.silent = None
        try:

            child = pexpect.spawn(command, args,timeout=60, echo=False,
                                  encoding='utf-8')
            # child.expect("\r\n")
            # self._write_to_stdout(magics['replsetip'])
            self.replwrapper = IREPLWrapper(
                                    self._write_to_stdout,
                                    self._write_to_stderr,
                                    self._read_from_stdin,
                                    child,
                                    replsetip=magics['replsetip'],
                                    orig_prompt='\r\n', 
                                    prompt_change=None,
                                    extra_init_cmd=None,
                                    line_output_callback=self.process_output)
            # child.expect("\r\n")
            # self._write_to_stdout(child.before)
            # child.expect("\r\n")
            # self._write_to_stdout(child.before)
            self.g_rtsps[str(self.replwrapper.child.pid)]=self.replwrapper
        except Exception as e:
            self._write_to_stderr("[Dart kernel] Error:Executable _start_replprg error! "+str(e)+"\n")

        finally:
            signal.signal(signal.SIGINT, sig)

    def process_output(self, output):
        if not self.silent:

            # Send standard output
            stream_content = {'name': 'stdout', 'text': output}
            self.send_response(self.iopub_socket, 'stream', stream_content)

    def send_replcmd(self, code, silent, store_history=True,
                   user_expressions=None, allow_stdin=False):
        self.silent = silent
        if not code.strip():
            return {'status': 'ok', 'execution_count': self.execution_count,
                    'payload': [], 'user_expressions': {}}

        interrupted = False
        try:
            # Note: timeout=None tells IREPLWrapper to do incremental
            # output.  Also note that the return value from
            # run_command is not needed, because the output was
            # already sent by IREPLWrapper.
            self._write_to_stdout("send command:"+code.rstrip()+"\n")
            self.replwrapper.run_command(code.rstrip(), timeout=None)
            pass
        except KeyboardInterrupt:
            self.gdbwrapper.child.sendintr()
            interrupted = True
            self.gdbwrapper._expect_prompt()
            output = self.gdbwrapper.child.before
            self.process_output(output)
        except EOF:
            # output = self.gdbwrapper.child.before + 'Restarting GDB'
            # self._start_gdb()
            # self.process_output(output)
            pass

        if interrupted:
            return {'status': 'abort', 'execution_count': self.execution_count}

        # try:
        #     exitcode = int(self.replwrapper.run_command('echo $?').rstrip())
        # except Exception as e:
        #     self.process_output("[Dart kernel] Error:Executable send_replcmd error! "+str(e)+"\n")
        exitcode = 0

        if exitcode:
            error_content = {'execution_count': self.execution_count,
                             'ename': '', 'evalue': str(exitcode), 'traceback': []}

            self.send_response(self.iopub_socket, 'error', error_content)
            error_content['status'] = 'error'
            return error_content
        else:
            return {'status': 'ok', 'execution_count': self.execution_count,
                    'payload': [], 'user_expressions': {}}
    #####################################################################
    def do_shell_command(self,commands,cwd=None,shell=True,magics=None):
        # self._write_to_stdout(''.join((' '+ str(s) for s in commands)))
        try:
            if len(magics['replcmdmode'])>0:
                findObj= commands[0].split(" ",1)
                if findObj and len(findObj)>1:
                    cmd=findObj[0]
                    arguments=findObj[1]
                    cmdargs=[]
                    for argument in re.findall(r'(?:[^\s,"]|"(?:\\.|[^"])*")+', arguments):
                        cmdargs += [argument.strip('"')]
                    self._write_to_stdout(cmd)
                    self._write_to_stdout(''.join((' '+ str(s) for s in cmdargs))+"\n")
                    self._start_replprg(cmd,cmdargs,magics)
                    return
            p = RealTimeSubprocess(commands,
                                  self._write_to_stdout,
                                  self._write_to_stderr,
                                  self._read_from_stdin,cwd,shell)
            self.g_rtsps[str(p.pid)]=p
            if magics!=None and len(magics['showpid'])>0:
                self._write_to_stdout("The process PID:"+str(p.pid)+"\n")
            while p.poll() is None:
                p.write_contents()
            # wait for threads to finish, so output is always shown
            p._stdout_thread.join()
            p._stderr_thread.join()
            del self.g_rtsps[str(p.pid)]
            p.write_contents()
            if p.returncode != 0:
                self._write_to_stderr("[Dart kernel] Error: Executable command exited with code {}\n".format(p.returncode))
            else:
                self._write_to_stdout("[Dart kernel] Info: command success.\n")
            return
        except Exception as e:
            self._write_to_stderr("[Dart kernel] Error:Executable command error! "+str(e)+"\n")

    def do_dart_command(self,commands=None,cwd=None,magics=None):
        p = self.create_jupyter_subprocess(['dart']+commands,cwd=os.path.abspath(''),shell=False)
        self.g_rtsps[str(p.pid)]=p
        if magics!=None and len(magics['showpid'])>0:
            self._write_to_stdout("The process PID:"+str(p.pid)+"\n")
        while p.poll() is None:
            p.write_contents()
        # wait for threads to finish, so output is always shown
        p._stdout_thread.join()
        p._stderr_thread.join()
        del self.g_rtsps[str(p.pid)]
        p.write_contents()

        if p.returncode != 0:
            self._write_to_stderr("[Dart kernel] Executable exited with code {}".format(p.returncode))
        else:
            self._write_to_stdout("[Dart kernel] Info:dart command success.")
        return

    def do_flutter_command(self,commands=None,cwd=None,magics=None):
        p = self.create_jupyter_subprocess(['flutter']+commands,cwd=os.path.abspath(''),shell=False)
        self.g_rtsps[str(p.pid)]=p
        if magics!=None and len(magics['showpid'])>0:
            self._write_to_stdout("The process PID:"+str(p.pid)+"\n")
        while p.poll() is None:
            p.write_contents()
        # wait for threads to finish, so output is always shown
        p._stdout_thread.join()
        p._stderr_thread.join()
        del self.g_rtsps[str(p.pid)]
        p.write_contents()

        if p.returncode != 0:
            self._write_to_stderr("[Dart kernel] Executable exited with code {}".format(p.returncode))
        else:
            self._write_to_stdout("[Dart kernel] Info:flutter command success.")
        return

    def send_cmd(self,pid,cmd):
        try:
            # self._write_to_stdout("send cmd PID:"+pid+"\n cmd:"+cmd)
            # if self.g_rtsps.has_key(pid):
                # self._write_to_stderr("[Dart kernel] Info:exist! "+pid+"\n")
            # self.g_rtsps[pid].stdin.write(cmd.encode())
            self.g_rtsps[pid]._write_to_stdout(cmd)
        except Exception as e:
            self._write_to_stderr("[Dart kernel] Error:Executable send_cmd error! "+str(e)+"\n")
    
        return
    def create_jupyter_subprocess(self, cmd,cwd=None,shell=False,env=None):
        try:
            return RealTimeSubprocess(cmd,
                                  self._write_to_stdout,
                                  self._write_to_stderr,
                                  self._read_from_stdin,cwd,shell,env)
        except Exception as e:
            self._write_to_stdout("RealTimeSubprocess err:"+str(e))
            raise
    def generate_dartfile(self, source_filename, binary_filename, cflags=None, ldflags=None):

        return

    def compile_with_dart2native(self, source_filename, binary_filename, cflags=None, ldflags=None):
        # cflags = ['-std=c89', '-pedantic', '-fPIC', '-shared', '-rdynamic'] + cflags
        # cflags = ['-std=c99', '-Wdeclaration-after-statement', '-Wvla', '-fPIC', '-shared', '-rdynamic'] + cflags
        # cflags = ['-std=iso9899:199409', '-pedantic', '-fPIC', '-shared', '-rdynamic'] + cflags
        # cflags = ['-std=c99', '-pedantic', '-fPIC', '-shared', '-rdynamic'] + cflags
        # cflags = ['-std=c11', '-pedantic', '-fPIC','-pie', '-rdynamic'] + cflags
        outfile=None
        #binary_filename='/root/mytestc.out'
        # if self.linkMaths:
        #     cflags = cflags + ['-lm']
        # if self.wError:
        #     cflags = cflags + ['-Werror']
        # if self.wAll:
        #     cflags = cflags + ['-Wall']
        #if ('-o' not in cflags):
            #binary_filename=cflags[cflags.index('-o')+1]
        #else:
        outfile= ['-o', binary_filename]
        args = ['dart','compile', 'exe', source_filename] + cflags + outfile + ldflags
        # for x in args: self._write_to_stderr(" " + x + " ")
        return self.create_jupyter_subprocess(args)

    def _filter_env(self, envstr):
        if envstr is None or len(envstr.strip())<1:
            return os.environ
        envstr=str(str(envstr.split("|")).split("=")).replace(" ","").replace("\'","").replace("\"","").replace("[","").replace("]","").replace("\\","")
        env_list=envstr.split(",")
        for i in range(0,len(env_list),2):
            os.environ.setdefault(env_list[i],env_list[i+1])
        return os.environ
    def _filter_magics(self, code):

        magics = {'cflags': [],
                  'ldflags': [],
                  'file': [],
                  'replcmdmode': [],
                  'replprompt': [],
                  'replsetip': "\r\n",
                  'showpid': [],
                  'norunnotecmd': [],
                  'noruncode': [],
                  'include': [],
                  'command': [],
                  'outputtype':'text/plain',
                  'env':None,
                  'fluttercmd': [],
                  'dartcmd': [],
                  'pid': [],
                  'pidcmd': [],
                  'args': []}

        actualCode = ''

        for line in code.splitlines():
            orgline=line
            if line.strip().startswith('//%'):
                if line.strip()[3:] == "noruncode":
                    magics['noruncode'] += ['true']
                    continue
                if line.strip()[3:] == "showpid":
                    magics['showpid'] += ['true']
                    continue
                if line.strip()[3:] == "replcmdmode":
                    magics['replcmdmode'] += ['replcmdmode']
                    continue
                if line.strip()[3:] == "replprompt":
                    magics['replprompt'] += ['replprompt']
                    continue
                if line.strip()[3:] == "onlyrunnotecmd":
                    magics['onlyrunnotecmd'] += ['true']
                    continue
                findObj= re.search( r':(.*)',line)
                if not findObj or len(findObj.group(0))<2:
                    continue
                key, value = line.strip()[3:].split(":", 2)
                key = key.strip().lower()

                if key in ['ldflags', 'cflags']:
                    for flag in value.split():
                        magics[key] += [flag]
                elif key == "file":
                    if len(value)>0:
                        magics[key] = value[re.search(r'[^/]',value).start():]
                    else:
                        magics[key] ='newfile'
                elif key == "include":
                    if len(value)>0:
                        magics[key] = value
                    else:
                        magics[key] =''
                        continue
                    if len(magics['include'])>0:
                        index1=line.find('//%')
                        line=self.readcodefile(magics['include'],index1)
                        actualCode += line + '\n'
                elif key == "pidcmd":
                    magics['pidcmd'] = [value]
                    if len(magics['pidcmd'])>0:
                        findObj= value.split(",",1)
                        if findObj and len(findObj)>1:
                            pid=findObj[0]
                            cmd=findObj[1]
                            self.send_cmd(pid=pid,cmd=cmd)
                elif key == "replsetip":
                    magics['replsetip'] = value
                elif key == "command" or key == "cmd":
                    magics['command'] = [value]
                    if len(magics['command'])>0:
                        self.do_shell_command(commands=magics['command'],magics=magics)
                elif key == "dartcmd":
                    for flag in value.split():
                        magics[key] += [flag]
                    if len(magics['dartcmd'])>0:
                        self.do_dart_command(magics['dartcmd'],magics=magics)
                elif key == "fluttercmd":
                    for flag in value.split():
                        magics[key] += [flag]
                    if len(magics['fluttercmd'])>0:
                        self.do_flutter_command(magics['fluttercmd'],magics=magics)
                elif key == "env":
                    envdict=self._filter_env(value)
                    magics[key] =dict(envdict)
                elif key == "outputtype":
                    magics[key]=value
                elif key == "args":
                    # Split arguments respecting quotes
                    for argument in re.findall(r'(?:[^\s,"]|"(?:\\.|[^"])*")+', value):
                        magics['args'] += [argument.strip('"')]

                # always add empty line, so line numbers don't change
                # actualCode += '\n'

            # keep lines which did not contain magics
            else:
                actualCode += line + '\n'

        return magics, actualCode

    # check whether int main() is specified, if not add it around the code
    # also add common magics like -lm
    def _add_main(self, magics, code):
        # remove comments
        tmpCode = re.sub(r"//.*", "", code)
        tmpCode = re.sub(r"/\*.*?\*/", "", tmpCode, flags=re.M|re.S)

        x = re.search(r".*\s+main\s*\(", tmpCode)

        if not x:
            code = self.main_head + code + self.main_foot
            magics['cflags'] += ['-v','error']

        return magics, code

    def do_execute(self, code, silent, store_history=True,
                   user_expressions=None, allow_stdin=True):
        
        magics, code = self._filter_magics(code)
        if len(magics['replcmdmode'])>0:
            return self.send_replcmd(code, silent, store_history=True,
                   user_expressions=None, allow_stdin=False)
        if len(magics['noruncode'])>0 and ( len(magics['command'])>0 or len(magics['dartcmd'])>0):
            return {'status': 'ok', 'execution_count': self.execution_count, 'payload': [], 'user_expressions': {}}
        if len(magics['file'])<1:
            magics, code = self._add_main(magics, code)
        
        with self.new_temp_file(suffix='.dart',dir=os.path.abspath('')) as source_file:
            source_file.write(code)
            source_file.flush()
            newsrcfilename=source_file.name
            
            if len(magics['file'])>0:
                newsrcfilename = magics['file']
                newsrcfilename = os.path.join(os.path.abspath(''),newsrcfilename)
                if os.path.exists(newsrcfilename):
                    newsrcfilename +=".new"
                if not os.path.exists(os.path.dirname(newsrcfilename)) :
                    os.makedirs(os.path.dirname(newsrcfilename))
                os.rename(source_file.name,newsrcfilename)
                self._write_to_stdout("[Dart kernel] Info:file "+ newsrcfilename +" created successfully\n")
        if len(magics['noruncode'])>0:
            return {'status': 'ok', 'execution_count': self.execution_count, 'payload': [], 'user_expressions': {}}
        
        p = self.create_jupyter_subprocess(['dart','--verbose',newsrcfilename]+ magics['args'],cwd=None,shell=False,env=magics['env'])
        #p = self.create_jupyter_subprocess([binary_file.name]+ magics['args'],cwd=None,shell=False)
        #p = self.create_jupyter_subprocess([self.master_path, binary_file.name] + magics['args'],cwd='/tmp',shell=True)
        self.g_rtsps[str(p.pid)]=p
        if magics!=None and len(magics['showpid'])>0:
            self._write_to_stdout("The process PID:"+str(p.pid)+"\n")
        while p.poll() is None:
            p.write_contents(magics)

        # wait for threads to finish, so output is always shown
        p._stdout_thread.join()
        p._stderr_thread.join()
        del self.g_rtsps[str(p.pid)]
        p.write_contents(magics)

        self.cleanup_files()
        if p.returncode != 0:
            self._write_to_stderr("[Dart kernel] Executable exited with code {}".format(p.returncode))
        return {'status': 'ok', 'execution_count': self.execution_count, 'payload': [], 'user_expressions': {}}

    def do_shutdown(self, restart):
        self.chk_replexit_thread.join()
        
        DartKernel.g_chkreplexit=False
        """Cleanup the created source code files and executables when shutting down the kernel"""
        self.cleanup_files()
