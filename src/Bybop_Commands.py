import os
import sys
import struct

MY_PATH, _ = os.path.split(os.path.realpath(__file__))
ARSDK_PATH=os.path.join(MY_PATH,'..', 'arsdk-xml')
ARCOMMANDS_PATH=os.path.join(ARSDK_PATH, 'xml')

sys.path.append(ARSDK_PATH)

import arsdkparser

_ctx = arsdkparser.ArParserCtx()
arsdkparser.parse_xml(_ctx, os.path.join(ARCOMMANDS_PATH, 'generic.xml'))
for f in sorted(os.listdir(ARCOMMANDS_PATH)):
    if not f.endswith('.xml') or f == 'generic.xml':
        continue
    arsdkparser.parse_xml(_ctx, os.path.join(ARCOMMANDS_PATH, f))
arsdkparser.finalize_ftrs(_ctx)


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
        if isinstance(arg.argType, arsdkparser.ArMultiSetting):
            raise Exception('Multisettings not supported !')
        elif isinstance(arg.argType, arsdkparser.ArBitfield):
            arg_str_type = arsdkparser.ArArgType.TO_STRING[arg.argType.btfType]
        elif isinstance(arg.argType, arsdkparser.ArEnum):
            arg_str_type = 'i32'
        else:
            arg_str_type = arsdkparser.ArArgType.TO_STRING[arg.argType]
        ret += _struct_fmt_for_type[arg_str_type]
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
    - s_cls  : Name of the class within the project (ignored for features)
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
    feat = None
    projid = 0
    cls = None
    clsid = 0
    cmd = None
    # Let an exception be raised if we do not know the command or if the format is bad
    # Find the project
    if s_proj in _ctx.projectsByName:
        proj = _ctx.projectsByName[s_proj]
    elif s_proj in _ctx.featuresByName:
        feat = _ctx.featuresByName[s_proj]
    if proj is None and feat is None:
        raise CommandError('Unknown project ' + s_proj)

    if proj: # Project
        projid = proj.projectId
        # Find the class
        if s_cls in proj.classesByName:
            cls = proj.classesByName[s_cls]
        if cls is None:
            raise CommandError('Unknown class ' + s_cls + ' in project ' + s_proj)
        clsid = cls.classId

        # Find the command
        if s_cmd in cls.cmdsByName:
            cmd = cls.cmdsByName[s_cmd]
        if cmd is None:
            raise CommandError('Unknown command ' + s_cmd + ' in class ' + s_cls + ' of project ' + s_proj)
    elif feat: # Feature
        projid = feat.featureId
        # Find the command
        if s_cmd in feat.cmdsByName:
            cmd = feat.cmdsByName[s_cmd]
        if cmd is None:
            raise CommandError('Unknown command ' + s_cmd + ' in feature ' + s_proj)

    ret = struct.pack('<BBH', projid, clsid, cmd.cmdId)
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


    return ret, cmd.bufferType, cmd.timeoutPolicy

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
    feat = None
    cls = None
    cmd = None
    # Let an exception be raised if we do not know the command or if the format is bad

    # Find the project
    if i_proj in _ctx.projectsById:
        proj = _ctx.projectsById[i_proj]
    # Or the feature
    if i_proj in _ctx.featuresById:
        feat = _ctx.featuresById[i_proj]

    # If project, Find the class
    if proj:
        if i_cls in proj.classesById:
            cls = proj.classesById[i_cls]
        else:
            return {}, False

        if i_cmd in cls.cmdsById:
            cmd = cls.cmdsById[i_cmd]
        else:
            return {}, False
    # If feature, find directly the command
    elif feat:
        if i_cmd in feat.cmdsById:
            cmd = feat.cmdsById[i_cmd]
        elif i_cmd in feat.evtsById:
            cmd = feat.evtsById[i_cmd]
        else:
            return {}, False
    else:
        return {}, False

    args = ()
    argsfmt, needed = _format_string_for_cmd(cmd)
    if needed:
        try:
            args = _struct_unpack(argsfmt, buf[4:])
        except struct.error:
            raise CommandError('Bad input buffers (arguments do not match the command)')

    ret = {
        'name'     : '%s.%s.%s' % (proj.name if proj else feat.name, cls.name if cls else '', cmd.name),
        'proj'     : proj.name if proj else feat.name,
        'class'    : cls.name if cls else '',
        'cmd'      : cmd.name,
        'listtype' : cmd.listType,
        'listtype_str' : arsdkparser.ArCmdListType.TO_STRING[cmd.listType],
        'args'     : {},
        'arg0'     : '',
    }

    for i in range(len(args)):
        if i == 0:
            ret['arg0'] = args[0]
        ret['args'][cmd.args[i].name] = args[i]

    return ret, True
