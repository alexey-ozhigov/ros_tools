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

options = {'OutputWarnings': False}

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

def resolve_ros_path_iter(path, ros_args):
	res = re.sub(re.compile('\$\(find'), '$(rospack find', path)
	res = re.sub(re.compile('\$\(arg robot\)'), '${ROBOT}', res)
	res = re.sub(re.compile('\$\(arg robot_env\)'), '${ROBOT_ENV}', res)
	for arg in ros_args.keys():
		res = re.sub(re.compile('\$\(arg ' + arg + '\)'), ros_args[arg], res)
	if path != res:
		return (res, True)
	else:
		return (res, False)

def resolve_ros_path(path, ros_args):
	#print 'resolving', path, 'args', str(ros_args)
	res = path
	while True:
		new_res, were_subst = resolve_ros_path_iter(res, ros_args)
		if not were_subst:
			break
		res = new_res
	#print 'resolved', new_res
	return new_res

def arg_str(entry):
	ret = 'arg ' + entry.attributes['name'].value + ' = '
	if entry.getAttribute('value'):
		ret += entry.attributes['value'].value
	if entry.getAttribute('default'):
		ret += '(' + entry.attributes['default'].value + ')'
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

def rosparam_str(entry):
        ret = 'rosparam: command "%s" file "%s"' % (entry.attributes['command'].value, entry.attributes['file'].value)
        if entry.attributes.has_key('ns'):
                ret += ' ns "%s"' % entry.attributes['ns'].value
        return ret

def print_internals(child_nodes, level, basen):
    for child in child_nodes:
        if child.nodeType == Node.ELEMENT_NODE:
            if child.nodeName == 'arg':
                print_entry(level, basen, arg_str(child))
            elif child.nodeName == '':
                print_entry(level, basen, arg_str(child))
	
def warn_message(msg):
        if options['OutputWarnings']:
                print >>stderr, msg

def browse_launch(dom, fname, includes, ros_args, basen = '', level = 1, recursive = True):
	global i_num
	for entry in dom.documentElement.childNodes:
                if entry.attributes and entry.attributes.has_key('if'):
                        warn_message('IF attribute not supported: %s: %s' % (fname, entry.toxml()))
		if entry.nodeType != Node.ELEMENT_NODE:
			continue
		if entry.nodeName == 'include':
			print_entry(level - 1, basen, include_str(entry))
                        #print all internal tags
                        print_internals(entry.childNodes, level, basen)
			if recursive:
                                resolved_fname = resolve_ros_path(entry.attributes['file'].value, ros_args)
                                includes[i_num] = resolved_fname
                                i_num += 1
                                include_fname = popen('echo -n ' + resolved_fname).read()
                                include_data = file(include_fname).read()
                                include_dom = parseString(include_data)
				browse_launch(include_dom, include_fname, includes, ros_args.copy(), basename(include_fname), level + 1, recursive)
		elif entry.nodeName == 'node':
			print_entry(level - 1, basen, node_str(entry))
                        print_internals(entry.childNodes, level, basen)
		elif entry.nodeName == 'arg':
			#Update ros_args for later substitutions into launch files
			if entry.getAttribute('default'):
				ros_args[entry.attributes['name'].value] = entry.attributes['default'].value
			if entry.getAttribute('value'):
				ros_args[entry.attributes['name'].value] = entry.attributes['value'].value
			print_entry(level - 1, basen, arg_str(entry))
                elif entry.nodeName == 'rosparam':
                        print_entry(level - 1, basen, rosparam_str(entry))
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
                                browse_launch(group_dom, fname, includes, ros_args.copy(), basename(fname), level, recursive)
		
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

def do_browse(fname, recursive, interactive):
	data = file(fname).read()
	dom = parseString(data)
	includes = {}
	ros_args = {}
	browse_launch(dom, fname, includes, ros_args, basename(fname), 1, recursive)
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
	do_browse(fname, recursive, interactive)
	#do_test()
