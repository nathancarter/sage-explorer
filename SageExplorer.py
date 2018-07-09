# -*- coding: utf-8 -*-
r"""
Sage Explorer in Jupyter Notebook

EXAMPLES ::
from SageExplorer import *
S = StandardTableaux(15)
t = S.random_element()
widget = SageExplorer(t)
display(t)

AUTHORS:
- Odile Bénassy, Nicolas Thiéry

"""
from ipywidgets import Layout, Box, VBox, HBox, Text, Label, HTML, Select, Textarea, Accordion, Tab, Button
import traitlets
from inspect import getdoc, getsource, getmembers, getmro, ismethod, isfunction, ismethoddescriptor, isclass
from cysignals.alarm import alarm, cancel_alarm, AlarmInterrupt
from sage.misc.sageinspect import sage_getargspec
from sage.all import *
import yaml, six, operator as OP

cell_layout = Layout(width='3em',height='2em', margin='0',padding='0')
box_layout = Layout()
css_lines = []
css_lines.append(".invisible {display: none; width: 0; height: 0}")
css_lines.append(".visible {display: table}")
css_lines.append(".titlebox {width: 40%}")
css_lines.append(".title {font-size: 150%}")
css_lines.append(".visualbox {min-height: 100px; padding: 15px}")
css_lines.append(".main {width: 100%}")
css_lines.append(".tabs {width: 100%}")
css_lines.append(".widget-text .widget-label {width: auto}")
css = HTML("<style>%s</style>"% '\n'.join(css_lines))
try:
    display(css)
except:
    pass # We are not in a notebook

TIMEOUT = 15 # in seconds
EXCLUDED_MEMBERS = ['__init__', '__repr__', '__str__']
EXPL_ROOT = '/home/odile/odk/sage/git/nthiery/odile/explorer'
OPERATORS = {'==' : OP.eq, '<' : OP.lt, '<=' : OP.le, '>' : OP.gt, '>=' : OP.ge}
CONFIG_ATTRIBUTES = yaml.load(open(EXPL_ROOT + "/attributes.yml").read())

def to_html(s):
    r"""Display nicely formatted HTML string
    INPUT: string s
    OUPUT: string
    """
    s = str(s)
    from sage.misc.sphinxify import sphinxify
    return sphinxify(s)

def method_origins(obj, names):
    """Return class where methods in list 'names' are actually defined
    INPUT: object 'obj', list of method names
    """
    c0 = obj
    if not isclass(c0):
        c0 = obj.__class__
    # Initialisation
    origins, overrides = {}, {}
    for name in names:
        origins[name] = c0
        overrides[name] = []
    for c in c0.__mro__[1:]:
        for name in names:
            if not name in [x[0] for x in getmembers(c)]:
                continue
            for x in getmembers(c):
                if x[0] == name:
                    if x[1] == getattr(c0, name):
                        origins[name] = c
                    else:
                        overrides[name].append(c)
    return origins, overrides

def extract_classname(c, element_ok=False):
    """Extract proper class name from class
    INPUT: class c
    OUTPUT: string

    TESTS::
    >> s = <class 'sage.combinat.tableau.StandardTableau'>
    >> extract_classname(s)
    StandardTableau
    >> s = <class 'sage.combinat.tableau.StandardTableaux_all_with_category.element_class'>
    >> extract_classname(s)
    StandardTableau
    """
    s = str(c.__name__)
    if ('element_class' in s or 'parent_class' in s) and not element_ok:
        s = str(c.__bases__[0])
    if s.endswith('>'):
        s = s[:-1]
        s = s.strip()
    if s.endswith("'"):
        s = s [:-1]
        s = s.strip()
    ret = s.split('.')[-1]
    if ret == 'element_class':
        return '.'.join(s.split('.')[-2:])
    return ret

def printed_attribute(obj, funcname):
    """Test whether this method, for this object,
    will be calculated at opening and displayed on this widget
    If True, return a label.
    INPUT: object obj, method name funcname
    OUTPUT: String or None"""
    if not funcname in CONFIG_ATTRIBUTES.keys():
        return
    config = CONFIG_ATTRIBUTES[funcname]
    if 'in' in config.keys():
        """Test in"""
        if not obj in eval(config['in']):
            return
    if 'not in' in config.keys():
        """Test not in"""
        if obj in eval(config['not in']):
            return
    def test_when(funcname, expected, operator=None, complement=None):
        res = getattr(obj, funcname)
        if operator and complement:
            res = operator(res, eval(complement))
        return (res == expected)
    def split_when(s):
        when_parts = config['when'].split()
        funcname = when_parts[0]
        if len(when_parts) > 2:
            operatorsign, complement = when_parts[1], when_parts[2]
        elif len(when_parts) > 1:
            operatorsign, complement = when_parts[1][0], when_parts[1][1:]
        if operatorsign in OPERATORS.keys():
            operator = OPERATORS[operatorsign]
        else:
            operator = "not found"
        return funcname, operator, complement
    if 'when' in config.keys():
        """Test when predicate(s)"""
        if isinstance(config['when'], six.string_types):
            when = [config['when']]
        elif isinstance(config['when'], (list,)):
            when = config['when']
        else:
            return
        for predicate in when:
            if not ' ' in predicate:
                if not hasattr(obj, predicate):
                    return
                if not test_when(predicate, True):
                    return
            else:
                funcname, operator, complement = split_when(predicate)
                if not hasattr(obj, funcname):
                    return
                if operator == "not found":
                    return
                if not test_when(funcname, True, operator, complement):
                    return
    if 'not when' in config.keys():
        """Test not when predicate(s)"""
        if isinstance(config['not when'], six.string_types):
            nwhen = [config['not when']]
            if not test_when(config['not when'],False):
                return
        elif isinstance(config['not when'], (list,)):
            nwhen = config['not when']
        else:
            return
        for predicate in nwhen:
            if not ' ' in predicate:
                if not test_when(predicate, False):
                    return
            else:
                funcname, operator, complement = split_when(predicate)
                if not test_when(funcname, False, operator, complement):
                    return
    if 'label' in config.keys():
        return config['label']
    return ' '.join([x.capitalize() for x in funcname.split('_')])

def display_attribute(label, res):
    return '%s: `%s <http://www.april.org>`_' % (label, res)


class SageExplorer(VBox):
    """Sage Explorer in Jupyter Notebook"""

    def __init__(self, obj):
        """
        TESTS::

        sage: S = StandardTableaux(15)
        sage: t = S.random_element()
        sage: widget = SageExplorer(t)
        """
        super(SageExplorer, self).__init__()
        self.title = Label()
        self.title.add_class('title')
        self.props = HTML()
        self.titlebox = VBox()
        self.titlebox.add_class('titlebox')
        self.titlebox.children = [self.title, self.props]
        self.visualbox = Box()
        self.visual = Textarea('', rows=8)
        self.visualbox.add_class('visualbox')
        self.visualbox.children = [self.visual]
        self.top = HBox([self.titlebox, self.visualbox])
        self.menus = Accordion()
        self.inputs = HBox()
        self.gobutton = Button(description='Run!', tooltip='Run the function or method, with specified arguments')
        self.output = HTML()
        self.worktab = VBox((self.inputs, self.gobutton, self.output))
        self.doc = HTML()
        self.doctab = HTML() # For the method docstring
        self.tabs = Tab((self.worktab, self.doctab)) # Will be used when a method is selected
        self.tabs.add_class('tabs')
        self.tabs.set_title(0, 'Main')
        self.tabs.set_title(1, 'Help')
        self.main = Box((self.doc, self.tabs))
        self.main.add_class('main')
        self.tabs.add_class('invisible') # Hide tabs at first display
        self.bottom = HBox((self.menus, self.main))
        self.children = (self.top, self.bottom)
        self.compute(obj)

    def init_selected_method(self):
        self.output.value = ''
        func = self.selected_func
        if isclass(func):
            self.doc.value = to_html(func.__doc__)
            self.doctab.value = ''
            self.inputs.children = []
            self.tabs.remove_class('visible')
            self.tabs.add_class('invisible')
            self.doc.remove_class('invisible')
            self.doc.add_class('visible')
            return
        self.doctab.value = to_html(func.__doc__)
        if self.overrides[func.__name__]:
            self.doctab.value += to_html("Overrides:")
            self.doctab.value += to_html(', '.join([extract_classname(x, element_ok=True) for x in self.overrides[func.__name__]]))
        inputs = []
        try:
            argspec = sage_getargspec(func)
            argnames, defaults = sage_getargspec(func).args, sage_getargspec(func).defaults
            shift = 0
            for i in range(len(argspec.args)):
                argname = argnames[i]
                if argname in ['self']:
                    shift = 1
                    continue
                default = ''
                if defaults and len(defaults) > i - shift and defaults[i - shift]:
                    default = argspec.defaults[i - shift]
                inputs.append(Text(description=argname, placeholder=str(default)))
        except:
            print func, "attr?"
            print argspec
        self.inputs.children = inputs
        self.doc.remove_class('visible')
        self.doc.add_class('invisible')
        self.tabs.remove_class('invisible')
        self.tabs.add_class('visible')

    def compute(self, obj):
        """Get some attributes, depending on the object
        Create links between menus and output tabs"""
        self.obj = obj
        self.visual.value = repr(obj._ascii_art_())
        c0 = obj.__class__
        self.classname = extract_classname(c0, element_ok=False)
        self.title.value = self.classname
        self.members = [x for x in getmembers(c0) if not x[0] in EXCLUDED_MEMBERS and (not x[0].startswith('_') or x[0].startswith('__')) and not 'deprecated' in str(type(x[1])).lower()]
        self.methods = [x for x in self.members if ismethod(x[1]) or ismethoddescriptor(x[1])]
        self.printed_attributes = []
        attribute_labels = {}
        for x in self.methods:
            if printed_attribute(obj, x[0]):
                self.printed_attributes.append(x)
                attribute_labels[x] = printed_attribute(obj, x[0])
        self.props.value = to_html('* ' + '\n* '.join([
            display_attribute(attribute_labels[x], getattr(obj, x[0])()) for x in self.printed_attributes]))
        self.doc.value = to_html(obj.__doc__) # Initialize to object docstring
        self.selected_func = c0
        origins, overrides = method_origins(c0, [x[0] for x in self.methods if not x in self.printed_attributes])
        self.overrides = overrides
        bases = []
        basemembers = {}
        for c in getmro(c0):
            bases.append(c)
            basemembers[c] = []
        for name in origins:
            basemembers[origins[name]].append(name)
        for c in basemembers:
            if not basemembers[c]:
                bases.remove(c)
            else:
                pass
                #print c, len(basemembers[c])
        menus = []
        for i in range(len(bases)):
            c = bases[i]
            menus.append(Select(rows=12,
                                options = [('----', c)] + [x for x in self.methods if x[0] in basemembers[c]]
            ))
        self.menus.children = menus
        for i in range(len(bases)):
            c = bases[i]
            self.menus.set_title(i, extract_classname(c))
        def menu_on_change(change):
            self.selected_func = change.new
            self.init_selected_method()
        for menu in self.menus.children:
            menu.observe(menu_on_change, names='value')
        def compute_selected_method(button):
            args = []
            for i in self.inputs.children:
                try:
                    arg = i.value or i.placeholder
                    if not arg:
                        self.output.value = to_html("Argument '%s' is empty!" % i.description)
                        return
                    args.append(arg)
                except:
                    self.output.value = to_html("Could not evaluate argument '%s'" % i.description)
                    return
            try:
                alarm(TIMEOUT)
                out = self.selected_func(obj, *args)
                cancel_alarm()
            except AlarmInterrupt:
                self.output.value = to_html("Timeout!")
            except Exception as e:
                self.output.value = to_html(e)
                return
            self.output.value = to_html(out)
        self.gobutton.on_click(compute_selected_method)

    def get_object(self):
        return self.obj

    def set_object(self, obj):
        self.obj = obj
        self.compute()
