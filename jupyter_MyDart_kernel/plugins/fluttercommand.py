from typing import Dict, Tuple, Sequence,List
from plugins.ISpecialID import IStag,IDtag,IBtag,ITag
import os
import re 
class MyFluttercommand(IStag):
    kobj=None
    def getName(self) -> str:
        # self.kobj._write_to_stdout("setKernelobj setKernelobj setKernelobj\n")
        
        return 'MyFluttercommand'
    def getAuthor(self) -> str:
        return 'Author'
    def getIntroduction(self) -> str:
        return 'MyFluttercommand'
    def getPriority(self)->int:
        return 0
    def getExcludeID(self)->List[str]:
        return []
    def getIDSptag(self) -> List[str]:
        return ['flutter','fluttercmd']
    def setKernelobj(self,obj):
        self.kobj=obj
        # self.kobj._write_to_stdout("setKernelobj setKernelobj setKernelobj\n")
        return
    def on_shutdown(self, restart):
        return
    def on_ISpCodescanning(self,key, value,magics,line) -> str:
        # self.kobj._write_to_stdout(line+" on_ISpCodescanning\n")
        self.kobj.addkey2dict(magics,'flutter')
        return self.commandhander(self,key, value,magics,line)
    ##在代码预处理前扫描代码时调用    
    def on_Codescanning(self,magics,code)->Tuple[bool,str]:
        pass
        return False,code
    ##生成文件时调用
    def on_before_buildfile(self,code,magics)->Tuple[bool,str]:
        return False,''
    def on_after_buildfile(self,returncode,srcfile,magics)->bool:
        return False
    def on_before_compile(self,code,magics)->Tuple[bool,str]:
        return False,''
    def on_after_compile(self,returncode,binfile,magics)->bool:
        return False
    def on_before_exec(self,code,magics)->Tuple[bool,str]:
        return False,''
    def on_after_exec(self,returncode,srcfile,magics)->bool:
        return False
    def on_after_completion(self,returncode,execfile,magics)->bool:
        return False
    def commandhander(self,key, value,magics,line):
        try:
            cmds=[]
            for argument in re.findall(r'(?:[^\s,"]|"(?:\\.|[^"])*")+', value.strip()):
                cmds += [argument.strip('"')]
            magics['flutter']=cmds
            if len(magics['flutter'])>0:
                self.do_flutter_command(self,commands=magics['flutter'],magics=magics)
        except Exception as e:
            self.kobj._logln("commandhander err:"+str(e))
        return ''
    def do_flutter_command(self,commands=None,cwd=None,magics=None):
        try:
            npmcmd=['flutter']
            if(self.kobj.sys=="Windows"):
                npmcmd=['cmd','/c','flutter']
            p = self.kobj.create_jupyter_subprocess(npmcmd+commands,cwd=cwd,shell=False,magics=magics)
            self.kobj.g_rtsps[str(p.pid)]=p
            if magics!=None and len(self.kobj.addkey2dict(magics,'showpid'))>0:
                self.kobj._logln("The process PID:"+str(p.pid))
            returncode=p.wait_end(magics)
            del self.kobj.g_rtsps[str(p.pid)]
            if returncode != 0:
                self.kobj._logln("Executable exited with code {}".format(returncode),3)
            else:
                self.kobj._logln("Info:flutter cmd command success.")
        except Exception as e:
            self.kobj._logln("commandhander err:"+str(e),3)
            raise
        return
        # magics['fluttercmd'] = value.strip()
        # if len(magics['fluttercmd'])>0:
        #     env=self.kobj.get_magicsSvalue(magics,'env')
        #     if len(env)<1:env=None
        #     self.kobj.do_Py_command(magics['fluttercmd'],env=env,magics=magics)
        # return ''
    
