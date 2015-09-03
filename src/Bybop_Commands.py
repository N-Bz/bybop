import os
import sys
import struct

# Find the path of the ARSDK
# We need this to get the ARCommandsParser module, which is located
# in the ARSDKBuildUtils repo, and the ARCommands XML files.

# User code can export the name before importing this module:
#   import os
#   os.environ['ARSDK_PATH'] = '/path/to/the/SDK'
#   import ARSDK_Commands

# This restriction might be lifted in further versions, by generating the command hierarchy
# beforehand, and importing this hierarchy in this module instead of reading the xml files each time.
# pickling the _projects variable is not a good way to do this, as we would still need the class
# descriptions found in the ARCommandsParser module, we will have to define our own!

try:
    ARSDK_PATH=os.environ['ARSDK_PATH']
except:
    print 'You need to export the path to the ARSDK3 in the ARSDK_PATH environment variable'
    sys.exit(1) # Ugly, but works
ARCOMMANDS_PATH=os.path.join(ARSDK_PATH, 'libARCommands')
PY_MODULES_PATH=os.path.join(ARSDK_PATH, 'ARSDKBuildUtils', 'Utils', 'Python')

sys.path.append(PY_MODULES_PATH)

from ARCommandsParser import *

_projects = parseAllProjects(['all'], ARCOMMANDS_PATH, False)

# Check all
_err = ''
for proj in _projects:
    _err = _err + proj.check()
if len (_err) > 0:
    print 'Your XML Files contain errors:',
    print _err
    sys.exit(1)


class CommandError(Exception):
    def __init__(self, msg):
        self.value = msg
    def __str__(self):
        return repr(self.value)

_struct_fmt_for_type = {
    'u8'     : 'B',
    'i8'     : 'b',
    'u16'    : 'H',
    'i16'    : 'h',
    'u32'    : 'I',
    'i32'    : 'i',
    'u64'    : 'Q',
    'i64'    : 'q',
    'float'  : 'f',
    'double' : 'd',
    'string' : 'z',
    'enum'   : 'i',
}

def _format_string_for_cmd(cmd):
    ret = '<'
    for arg in cmd.args:
        ret += _struct_fmt_for_type[arg.type]
    return ret, bool(cmd.args)

def _struct_pack(fmt, *args):
    """
    like struct.pack(fmt, *args)
    except that a 'z' format is supported to include null terminated strings
    """
    nbarg = 0
    real_fmt = ''
    for c in fmt:
        if c == 'z':
            real_fmt += '%ds' % (len(args[nbarg])+1)
            nbarg += 1
        else:
            real_fmt += c
            if c in 'cbB?hHiIlLqQfdspP':
                nbarg += 1
    return struct.pack(real_fmt, *args)


def _struct_unpack(fmt, string):
    """
    like struct.unpack(fmt, string)
    except that a 'z' format is supported to read a null terminated string
    """
    real_fmt=''
    null_idx=[]
    nbarg = 0
    for i in range(len(fmt)):
        c = fmt[i]
        if c == 'z':
            start = struct.calcsize(real_fmt)
            strlen = string[start:].find('\0')
            if strlen < 0:
                raise CommandError('No null char in string')
            real_fmt += '%dsB' % strlen
            nbarg += 1
            null_idx.append(nbarg)
            nbarg += 1
        else:
            real_fmt += c
            if c in 'cbB?hHiIlLqQfdspP':
                nbarg += 1

    content = struct.unpack(real_fmt, string)
    ret = tuple([content[i] for i in range(len(content)) if i not in null_idx])
    return ret

def pack_command(s_proj, s_cls, s_cmd, *args):
    """
    Pack a command into a string.

    Arguments:
    - s_proj : Name of the project
    - s_cls  : Name of the class within the project
    - s_cmd  : Name of the command within the class
    - *args  : Arguments of the command.

    If the project, the class or the command can not be found in the command table,
    a CommandError will be raised.

    If the number and type of arguments in *arg do not match the expected ones, a
    CommandError will be raised.

    Return the command string, the command recommanded buffer and the command
    recommanded timeout policy.
    """
    proj = None
    cls = None
    cmd = None
    cmdid = 0
    # Let an exception be raised if we do not know the command or if the format is bad
    # Find the project
    for project in _projects:
        if project.name == s_proj:
            proj = project
            break
    if proj is None:
        raise CommandError('Unknown project ' + s_proj)
    # Find the class
    for test_class in proj.classes:
        if test_class.name == s_cls:
            cls = test_class
            break
    if cls is None:
        raise CommandError('Unknown class ' + s_cls + ' in project ' + s_proj)
    # Find the command
    for i in range(len(cls.cmds)):
        test_cmd = cls.cmds[i]
        if test_cmd.name == s_cmd:
            cmd = test_cmd
            cmdid = i
            break
    if cmd is None:
        raise CommandError('Unknown command ' + s_cmd + ' in class ' + s_cls + ' of project ' + s_proj)

    ret = struct.pack('<BBH', int(proj.ident), int(cls.ident), cmdid)
    argsfmt, needed = _format_string_for_cmd(cmd)
    if needed:
        try:
            ret += _struct_pack(argsfmt, *args)
        except IndexError:
            raise CommandError('Missing arguments')
        except TypeError:
            raise CommandError('Bad type for arguments')
        except struct.error:
            raise CommandError('Bad type for arguments')
            
        
    return ret, cmd.buf, cmd.timeout

def unpack_command(buf):
    """
    Unpack a command string into a dictionnary of arguments

    Arguments:
    - buf : The packed command

    Return a dictionnary describing the command, and a boolean indicating whether the
    command is known. If the boolean is False, then the dictionnary is {}

    Return dictionnary format:
    {
      'name' : full name of the command (project.class.command)
      'project' : project of the command
      'class' : class of the command
      'cmd' : command name
      'listtype' : list type (none/list/map) of the command
      'args' : arguments in the commands, in the form { 'name':value, ... }
      'arg0' : value of the first argument ('' if no arguments)
               this is useful for map commands, as this will be the key.
    }

    A CommandError is raised if the command is in a bad format.
    """
    # Read the project/cls/cmd from the buffer
    try:
        (i_proj, i_cls, i_cmd) = struct.unpack('<BBH', buf[:4])
    except struct.error:
        raise CommandError('Bad input buffer (not an ARCommand)')
    proj = None
    cls = None
    cmd = None
    # Let an exception be raised if we do not know the command or if the format is bad

    # Find the project
    for project in _projects:
        if int(project.ident) == i_proj:
            proj = project
            break
    if proj is None:
        return {}, False
    # Find the class
    for test_class in proj.classes:
        if int(test_class.ident) == i_cls:
            cls = test_class
            break
    if cls is None:
        return {}, False
    # Commands are in order in their classes
    try:
        cmd = cls.cmds[i_cmd]
    except IndexError:
        return {}, False


    args = ()
    argsfmt, needed = _format_string_for_cmd(cmd)
    if needed:
        try:
            args = _struct_unpack(argsfmt, buf[4:])
        except struct.error:
            raise CommandError('Bad input buffers (arguments do not match the command)')

    ret = {
        'name'     : '%s.%s.%s' % (proj.name, cls.name, cmd.name),
        'proj'     : proj.name,
        'class'    : cls.name,
        'cmd'      : cmd.name,
        'listtype' : cmd.listtype,
        'args'     : {},
        'arg0'     : '',
    }

    for i in range(len(args)):
        if i == 0:
            ret['arg0'] = args[0]
        ret['args'][cmd.args[i].name] = args[i]

    return ret, True
