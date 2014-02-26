#!/usr/bin/python

from xml.dom.minidom import parseString, Node
import re
from os import popen
from os import system
from os.path import basename
from sys import argv
from sys import stderr
from xml.parsers.expat import ExpatError

FNAME = 'robot.launch'
EDITOR = 'vim'

XML_HEADER = '<?xml version="1.0"?>'

default_options = {\
                    'output_warnings': False,\
                    'substitute_variables': False,\
                    'show_params': False,\
                  }

def print_entry(level, basen, *args):
	begc =  bcolors.OKBLUE
	endc = bcolors.ENDC
	pref = '%-40s' % basen + ' ' * level if level > 0 else '%-40s' % basen
	body = ''
	for arg in args:
		body += arg
	print begc + pref + endc, body	

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    def disable(self):
        self.HEADER = ''
        self.OKBLUE = ''
        self.OKGREEN = ''
        self.WARNING = ''
        self.FAIL = ''
        self.ENDC = ''

def subst_ros_arg(ros_args, key, value, overwrite):
        if overwrite.has_key(key):
                ros_args[key] = overwrite[key] 
        else:
                ros_args[key] = value

def eval_ros_str_iter(path, ros_args, subst_values, debug=False):
        res = path
        #[(pattern, replace), ...]
        subst_seq = [\
                    ('\$\(find', '$(rospack find'),\
                    ('\$\(env ROBOT_ENV.*?\)', '${ROBOT_ENV}'),\
                    ('\$\(optenv ROBOT_ENV.*?\)', '${ROBOT_ENV}'),\
                    ('\$\(optenv ROBOT.*?\)', '${ROBOT}'),\
                    ('\$\(env ROBOT.*?\)', '${ROBOT}')\
                    ]
        for subst in subst_seq:
            if debug:
                print 'eval_ros_str_iter BEFORE:', res, 'PAT:', subst[0]
            res = re.sub(re.compile(subst[0]), subst[1], res)
            if debug:
                print 'eval_ros_str_iter AFTER:', res
	for arg in ros_args.keys():
                value = subst_values[arg] if subst_values and subst_values.has_key(arg) else ros_args[arg]
                if debug:
                    print 'eval_ros_str_iter BEFORE:', res, 'ARG:', arg, 'VAL:', value
		res = re.sub(re.compile('\$\(arg ' + arg + '\)'), value, res)
                if debug:
                    print 'eval_ros_str_iter AFTER:', res
	if path != res:
		return (res, True)
	else:
		return (res, False)

def eval_ros_str(path, ros_args, subst_values, debug=False):
	#print 'resolving', path, 'args', str(ros_args)
	res = path
	while True:
		new_res, were_subst = eval_ros_str_iter(res, ros_args, subst_values)
		if not were_subst:
			break
		res = new_res
	#print 'resolved', new_res
	return new_res, were_subst

def arg_str(entry):
	ret = 'arg ' + entry.attributes['name'].value + ' = '
	if entry.getAttribute('value'):
		ret += entry.attributes['value'].value
	if entry.getAttribute('default'):
		ret += entry.attributes['default'].value
	return ret

i_num = 1

def include_str(entry):
	begc =  bcolors.OKGREEN
	endc = bcolors.ENDC
	return 'include' + begc + str(i_num) + endc + ': ' + entry.attributes['file'].value

def node_str(entry):
	ret = 'node: name "%s" pkg "%s" type "%s"' % (entry.attributes['name'].value,
				              entry.attributes['pkg'].value,
				              entry.attributes['type'].value)
	return ret

def group_str(entry):
	ret = 'group: '
        if entry.attributes.has_key('if'):
                ret += 'condition "%s"' % entry.attributes['if'].value
        if entry.attributes.has_key('ns'):
                ret += 'ns "%s"' % entry.attributes['ns'].value
        return ret

def rosparam_str(entry, ros_args, options, debug = False):
        fname = ''
        do_fname = False
        ret = 'rosparam: '
        if debug:
            print 'rosparam_str BEFORE:', entry.toxml()
        if entry.attributes.has_key('command'):
            command_val = entry.attributes['command'].value
            print command_val
            ret += 'command "%s" ' % command_val
            if command_val == 'load':
                print 'do_fname'
                do_fname = True
        if entry.attributes.has_key('file'):
            (resolved_fname, were_subst) = eval_ros_str(entry.attributes['file'].value, ros_args, options['subst_values'], debug=debug)
            if debug:
                print 'rosparam_str AFTER:', resolved_fname
            ret += 'file "%s" ' % resolved_fname
            if do_fname:
                fname = resolved_fname
                print fname
        if entry.attributes.has_key('ns'):
                ret += 'ns "%s" ' % entry.attributes['ns'].value
        return (ret, fname)

def param_str(entry, fname, ros_args, options):
    #NOTE: only name and value attributes supported
    (name, _) = eval_ros_str(entry.attributes['name'].value, ros_args, options['subst_values'])
    if entry.attributes.has_key('value'):
        value = entry.attributes['value'].value
        (value, _) = eval_ros_str(value, ros_args, options['subst_values'])
    else:
        value = '<UNK>'
        warn_message('file attrs for param tag not supported', fname, entry, options)
    return 'param: %s = %s' % (name, value)

def print_internals(child_nodes, level, basen):
    for child in child_nodes:
        if child.nodeType == Node.ELEMENT_NODE:
            if child.nodeName == 'arg':
                print_entry(level, basen, arg_str(child))
            elif child.nodeName == '':
                print_entry(level, basen, arg_str(child))
	
def warn_message(msg, fname, entry, options):
        if options['output_warnings']:
            print >>stderr, '%s: %s:\n %s' % (fname, entry.toxml(), msg)

def browse_launch(dom, fname, includes, ros_args, options, params, param_fnames, basen = '', level = 1, recursive = True):
    global i_num
    for entry in dom.documentElement.childNodes:
        if entry.attributes and entry.attributes.has_key('if'):
            warn_message('IF attribute not supported', fname, entry, options)
        if entry.nodeType != Node.ELEMENT_NODE:
                continue
        if entry.nodeName == 'include':
            print_entry(level - 1, basen, include_str(entry))
            #print all internal tags
            print_internals(entry.childNodes, level, basen)
            if recursive:
                (resolved_fname, _) = eval_ros_str(entry.attributes['file'].value, ros_args, options['subst_values'])
                includes[i_num] = resolved_fname
                i_num += 1
                include_fname = popen('echo -n ' + resolved_fname).read()
                include_data = file(include_fname).read()
                include_dom = parseString(include_data)
                browse_launch(include_dom, include_fname, includes, ros_args.copy(), options, params, param_fnames, basename(include_fname), level + 1, recursive)
        elif entry.nodeName == 'node':
            print_entry(level - 1, basen, node_str(entry))
            print_internals(entry.childNodes, level, basen)
            if recursive:
                #NOTE: Not optimal: parseString is called second time for the same data
                node_data = ''
                for child in entry.childNodes:
                    child_str = child.toxml()
                    if child_str != '':
                        node_data += child_str
                #warping into fake_group tags is done because minidom requires a root tag
                node_data = '<fake_group>' + node_data + '</fake_group>'
                node_data = XML_HEADER + '\n' + node_data
                node_dom = parseString(node_data)
                browse_launch(node_dom, fname, includes, ros_args.copy(), options, params, param_fnames, basename(fname), level, recursive)
        elif entry.nodeName == 'arg':
            #Update ros_args for later substitutions into launch files
            if entry.getAttribute('default'):
                ros_args[entry.attributes['name'].value] = entry.attributes['default'].value
                if entry.getAttribute('value'):
                    ros_args[entry.attributes['name'].value] = entry.attributes['value'].value
                #If -v command line param is supplied (dictionary), use the given value
                if options['subst_values'] != None:
                    subst_ros_arg(ros_args[entry.attributes['name'].value], entry.attributes['value'].value, options['subst_values'])
                print_entry(level - 1, basen, arg_str(entry))
        elif entry.nodeName == 'rosparam':
            (s, fname) = rosparam_str(entry, ros_args, options, debug=True)
            print_entry(level - 1, basen, s)
            if fname != '':
                param_fnames.append(fname)
        elif entry.nodeName == 'param':
            print_entry(level - 1, basen, param_str(entry, fname, ros_args, options))
        elif entry.nodeName == 'group':
            print_entry(level - 1, basen, group_str(entry))
            print_internals(entry.childNodes, level, basen)
            if recursive:
                #NOTE: Not optimal: parseString is called second time for the same data
                group_data = ''
                for child in entry.childNodes:
                    child_str = child.toxml()
                    if child_str != '':
                        group_data += child_str
                #warping into fake_group tags is done because minidom requires a root tag
                group_data = '<fake_group>' + group_data + '</fake_group>'
                group_data = XML_HEADER + '\n' + group_data
                group_dom = parseString(group_data)
                browse_launch(group_dom, fname, includes, ros_args.copy(), options, params, param_fnames, basename(fname), level, recursive)
    return param_fnames
            
def cmd_loop(includes):
	while True:
		try:
			n = raw_input('n> ')
		except:
			return
		try:
			n = int(n)
			assert n > 0 and n <= len(includes)
		except:
			print >>stderr, 'Usage: <n>, where <n> is include number'
			continue
		editor_cmd = EDITOR + ' ' + includes[n]
		system(editor_cmd)

def do_browse(fname, options, recursive, interactive):
	data = file(fname).read()
	dom = parseString(data)
	includes = {}
	ros_args = {}
	param_fnames = browse_launch(dom, fname, includes, ros_args, options, {}, [], basename(fname), 1, recursive)
        if options['show_params']:
            for fname in param_fnames:
                print '\n\nparamfile %s' % fname
                print popen('cat %s' % fname).read()
	if interactive:
		cmd_loop(includes)

def do_test():
        #test_str = '<rosparam command="load" file="$(find mcr_default_env_config)/$(arg robot_env)/speech_objects.yaml"/><rosparam command="load" file="$(find mcr_default_env_config)/$(arg robot_env)/speech_objects.yaml"/>'
        test_str = '<a attr1="attr_value1" /> <b attr1="attr_value2" />'

        print test_str
        dom = parseString(test_str)
	#dom = parseString('<a file="f.txt"> <node type="nodetype" /> </a>')
	for child in dom.childNodes:
		print child.nodeName, child.nodeValue, child.hasAttributes()
		for child2 in child.childNodes:
			if child2.nodeType != Node.TEXT_NODE:
				print child2.nodeName
def do_test2():
    s = '$(rospack find cob_navigation_config)/${ROBOT}/costmap_common_params.yaml'
    fname = eval_ros_str(s, {}, {}, debug=True)[0]
    print popen('cat %s' % fname).read()


if __name__ == '__main__':
	try:
		if argv.index('-r') >= 0:
			recursive = True
	except:
		recursive = False
	try:
		if argv.index('-i') >= 0:
			interactive = True
	except:
		interactive = False
	try:
		fname = argv[1]
	except:
		fname = FNAME
        options = default_options
        try:
                ind = argv.index('-v')
                if ind >= 0 and ind < len(argv) - 1:
                        subst_values = eval(argv[ind - 1])
        except:
                subst_values = None
        try:
                ind = argv.index('-p')
                if ind >= 0 and ind < len(argv):
                        show_params = True
        except:
                show_params = default_options['show_params']
        options['subst_values'] = subst_values
        options['show_params'] = show_params
        do_browse(fname, options, recursive, interactive)
        #do_test2()
