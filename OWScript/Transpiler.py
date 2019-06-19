from collections import defaultdict
from itertools import count
from string import capwords

try:
    from . import Errors
    from .AST import *
    from .Tokens import ALIASES
except ImportError:
    from AST import *

class Scope:
    def __init__(self, name, parent=None, namespace=None):
        self.name = name
        self.parent = parent
        self.namespace = namespace or {}

    def get(self, name, default=None):
        value = self.namespace.get(name, default)
        if value is not None:
            if not (type(value) == GlobalVar and value.name == name):
                return value
        if self.parent:
            return self.parent.get(name, default)

    def set(self, name, value):
        self.namespace[name] = value

    def __repr__(self):
        return f"<Scope '{self.name}'>{self.parent or ''}"

class Builtin:
    def range_(tp, args):
        args = map(tp.visit, args)
        elements = list(map(lambda n: Numeral(value=str(n)), (range(*map(int, args)))))
        array = Array(elements=elements)
        return array

    def ceil(tp, n):
        node = OWID(name='Round To Integer')
        node.children.extend([*n, OWID(name='Up')])
        return node

    def floor(tp, n):
        node = OWID(name='Round To Integer')
        node.children.extend([*n, OWID(name='Up')])
        return node

    functions = {
        'range': range_,
        'ceil': ceil,
        'floor': floor
    }

class Transpiler:
    def __init__(self, tree, indent_size=3):
        self.tree = tree
        self.indent_size = indent_size
        self.indent_level = 0
        self.global_vars = {}
        self.player_vars = {}
        self.global_index = count()
        self.player_index = defaultdict(count)
        self.pointer_index = 0
        self.line = 0
        self.functions = Builtin.functions
        self.arrays = {}
        self.scope = Scope(name='global')
        self.aliases = {k: v for d in ALIASES.values() for k, v in d.items()}

    @property
    def tabs(self):
        return ' ' * self.indent_size * self.indent_level

    def parse_string(self, strings):
        code = '"'
        for name in strings:
            value = self.scope.get(name, name)
            if type(value) != str:
                value = value.value[0]
            code += value.replace('"', '').replace("'", '').replace('`', '')
        return code + '"'

    def assign(self, node, value):
        code = ''
        name = node.name
        if type(node) == GlobalVar:
            index = self.global_vars.get(name)
            if index is None:
                index = next(self.global_index)
                self.global_vars[name] = index
            code += f'Set Global Variable At Index(A, {index}, '
        elif type(node) == PlayerVar:
            player = node.player
            index = self.player_vars.get((player, name))
            if index is None:
                index = next(self.player_index[player])
                self.player_vars[(player, name)] = index
            code += f'Set Player Variable At Index({player}, A, {index}, '
        code += self.visit(value) + ')'
        return code

    def lookup(self, node):
        name = node.name
        if type(node) == GlobalVar:
            index = self.global_vars.get(name)
            if index is None:
                index = self.global_vars[name] = next(self.global_index)
            return index
        elif type(node) == PlayerVar:
            player = node.player
            index = self.player_vars.get((player, name))
            if index is None:
                index = self.player_vars[(player, name)] = next(self.player_index[player])
            return index

    def visitScript(self, node):
        code = r'rule("Generated by https://github.com/adapap/OWScript") { Event { Ongoing - Global; }}' + '\n'
        return (code + self.visitChildren(node)).rstrip('\n')

    def visitRule(self, node):
        code = ''
        if node.disabled:
            code += 'disabled '
        code += 'rule('
        code += self.parse_string(node.name.value)
        code += ') {\n' + self.visitChildren(node) + '}\n'
        return code

    def visitFunction(self, node):
        self.functions[node.name] = node
        return ''

    def visitBlock(self, node):
        self.indent_level += 1
        code = self.visitChildren(node)
        self.indent_level -= 1
        return code

    def visitRuleblock(self, node):
        code = self.tabs + node.name + ' {\n'
        self.indent_level += 1
        for ruleblock in node.children:
            for line in ruleblock.children:
                code += self.tabs + self.visit(line)
                if node.name.upper() == 'CONDITIONS':
                    code += ' == True'
                code += ';\n'
        self.indent_level -= 1
        code += self.tabs + '}\n'
        return code

    def visitOWID(self, node):
        code = self.aliases.get(node.name.upper(), node.name).title()
        if node.children:
            children = [self.visit(child) for child in node.children]
            if code == 'Wait' and len(children) == 1:
                children.append('Ignore Condition')
            code += '(' + ', '.join(children) + ')'
        return code

    def visitConst(self, node):
        return node.value

    def visitCompare(self, node):
        if node.op.lower() == 'in':
            return 'Array Contains(' + self.visit(node.right) + ', ' + self.visit(node.left) + ')'
        elif node.op.lower() == 'not in':
            return 'Not(Array Contains(' + self.visit(node.right) + ', ' + self.visit(node.left) + '))'
        return 'Compare(' + self.visit(node.left) + f', {node.op}, ' + self.visit(node.right) + ')'

    def visitAssign(self, node):
        code = ''
        value = node.right
        if type(node.left) == GlobalVar:
            node.left = self.scope.get(node.left.name) or node.left
        name = node.left.parent.name if type(node.left) in (Item,) else node.left.name
        if type(value) == Array:
            self.arrays[name] = value
            value = Array(elements=[x for x in value.elements if type(x) != String])
        elif type(value) == Call:
            function = self.functions[value.parent.name]
            if type(function) != Function:
                result = function(self, value.args)
                if type(result) == Array:
                    self.arrays[name] = result
        value = {
            '+=': BinaryOp(left=node.left, op='+', right=value),
            '-=': BinaryOp(left=node.left, op='-', right=value),
            '*=': BinaryOp(left=node.left, op='*', right=value),
            '/=': BinaryOp(left=node.left, op='/', right=value),
            '^=': BinaryOp(left=node.left, op='^', right=value),
            '%=': BinaryOp(left=node.left, op='%', right=value)
        }.get(node.op, value)
        if type(node.left) not in (GlobalVar, PlayerVar, Item):
            raise Errors.SyntaxError('Invalid variable type in assignment')
        if type(node.left) == Item:
            item = node.left
            index = self.lookup(node=item.parent)
            try:
                array_index = int(self.visit(item.index))
            except ValueError:
                raise Errors.SyntaxError('Array modification index must be an integer')
            self.arrays[name][array_index] = value
            code += f'Set Global Variable(B, {self.visit(item.parent)});\n'
            if type(value) == Array:
                raise Errors.NotImplementedError('Array modification cannot be used for nested arrays')
            code += self.tabs + f'Set Global Variable At Index(B, {array_index}, {self.visit(value)});\n'
            code += self.tabs + f'Set Global Variable At Index(A, {index}, Global Variable(B))'
            return code
        code += self.assign(node=node.left, value=value)
        return code

    def visitIf(self, node):
        cond = self.visit(node.cond)
        skip_code = 'Skip If(Not({}), {});\n'
        skip_false = ''
        true_code = ''
        false_code = ''
        for line in node.true_block.children:
            true_code += self.tabs + self.visit(line) + ';\n'
        if node.false_block:
            skip_false += self.tabs + 'Skip({});\n'
            if type(node.false_block) == If:
                false_code += self.tabs + self.visit(node.false_block)
            else:
                for line in node.false_block.children:
                    false_code += self.tabs + self.visit(line) + ';\n'
        skip_code = skip_code.format(cond, true_code.count(';\n') + bool(node.false_block))
        if false_code:
            skip_false = skip_false.format(false_code.count(';\n') + bool(type(node.false_block) == If))
        code = skip_code + true_code + skip_false + false_code
        return code.rstrip(';\n')

    def visitWhile(self, node):
        lines = len(node.body.children) + 2
        code = f'Skip If(Not({self.visit(node.cond)}), {lines});\n'
        for line in node.body.children:
            code += self.tabs + self.visit(line) + ';\n'
        code += f'{self.tabs}Wait(0.001, Ignore Condition);\n'
        code += f'{self.tabs}Loop If({self.visit(node.cond)})'
        return code

    def visitFor(self, node):
        code = ''
        pointer = node.pointer
        iterable = None
        if type(node.iterable) == Call:
            function = self.functions[node.iterable.parent.name]
            if type(function) != Function:
                result = function(self, node.iterable.args)
                if type(result) == Array:
                    iterable = result
        elif node.iterable.name in self.arrays:
            iterable = self.arrays.get(node.iterable.name)
        if iterable:
            lines = []
            for elem in iterable:
                scope = Scope(name='for', parent=self.scope, namespace={pointer: elem})
                for child in node.body.children:
                    lines.append(self.visit(child, scope=scope))
            code += (';\n' + self.tabs).join(lines)
        else:
            raise NotImplementedError('Overwatch types not supported in loops yet')
        return code

    def visitBinaryOp(self, node):
        code = {
            '+': 'Add',
            '-': 'Subtract',
            '*': 'Multiply',
            '/': 'Divide',
            '^': 'Raise To Power',
            '%': 'Modulo',
            'or': 'Or',
            'and': 'And'
        }.get(node.op)
        code += '(' + self.visit(node.left) + ', ' + self.visit(node.right) + ')'
        return code

    def visitUnaryOp(self, node):
        if node.op == '-':
            code = '-' + self.visit(node.right)
        elif node.op == 'not':
            code = 'Not(' + self.visit(node.right) + ')'
        return code

    def visitGlobalVar(self, node):
        if self.scope.namespace.get(node.name):
            value = self.scope.namespace.get(node.name)
            result = self.visit(value, scope=self.scope.parent)
            return result
        index = self.lookup(node=node)
        return f'Value In Array(Global Variable(A), {index})'

    def visitPlayerVar(self, node):
        index = self.lookup(node=node)
        code = f'Value In Array(Player Variable(' + self.visit(node.player) + f', A), {index})'
        return code

    def visitString(self, node):
        code = 'String('
        code += self.parse_string(node.value)
        children = [', ' + self.visit(child) for child in node.children]
        code += ''.join(children)
        if len(children) < 3:
            code += ', ' + ', '.join(['Null'] * (3 - len(children)))
        return code + ')'

    def visitNumeral(self, node):
        return node.value

    def visitTime(self, node):
        time = node.value
        if time.endswith('ms'):
            time = float(time.rstrip('ms')) / 1000
        elif time.endswith('s'):
            time = float(time.rstrip('s'))
        elif time.endswith('min'):
            time = float(time.rstrip('min')) * 60
        return str(round(time, 3))

    def visitVector(self, node):
        code = 'Vector('
        components = ', '.join(self.visit(x) for x in node.children)
        code += components + ')'
        return code

    def visitArray(self, node):
        if not node.elements:
            return 'Empty Array'
        else:
            owid_has_child = lambda x: True if type(x) != OWID else len(x.children) > 0
            valid_elems = [x for x in node.elements if owid_has_child(x)]
            num_elems = len(valid_elems)
            if num_elems == 0:
                return 'Empty Array'
            code = 'Append To Array(' * num_elems
            code += 'Empty Array, ' + '), '.join(self.visit(elem) for elem in valid_elems) + ')'
        return code

    def visitItem(self, node):
        if node.parent.name in self.arrays:
            array = self.arrays[node.parent.name]
            index = None
            try:
                index = int(node.index)
            except TypeError:
                try:
                    index = int(self.visit(node.index))
                except ValueError:
                    return 'Value In Array(' + self.visit(node.parent) + ', ' + self.visit(node.index) + ')'
            except ValueError:
                index = int(self.visit(node.index))
            item = array[index]
            if type(item) == str:
                return item
            if type(item) not in (OWID, String, Numeral):
                return self.visit(item, scope=self.scope.parent)
            return self.visit(item)
        return 'Value In Array(' + self.visit(node.parent) + ', ' + self.visit(node.index) + ')'

    def visitAttribute(self, node):
        attribute = {
            'x': 'X Component Of({})',
            'y': 'Y Component Of({})',
            'z': 'Z Component Of({})',
            'facing': 'Facing Direction Of({})',
            'pos': 'Position Of({})',
            'eyepos': 'Eye Position({})',
            'hero': 'Hero Of({})',
            'jumping': 'Is Button Held({}, Jump)',
            'crouching': 'Is Button Held({}, Crouch)',
            'interacting': 'Is Button Held({}, Interact)',
            'lmb': 'Is Button Held({}, Primary Fire)',
            'rmb': 'Is Button Held({}, Secondary Fire)',
            'moving': 'Compare(Speed Of({}), >, 0)'
        }.get(node.name.lower())
        code = attribute.format(self.visit(node.parent))
        return code

    def visitCall(self, node):
        callee = node.parent
        args = list(map(self.visit, node.args))
        code = ''
        if type(callee) == Attribute:
            method = callee.name
            arity = {
                'append': 1,
                'index': 1,
                'halt': 0
            }
            try:
                assert len(args) == arity.get(method)
            except AssertionError:
                raise Errors.SyntaxError('{} expected {} parameter, received {}'.format(method, arity.get(method), len(args)))
            if method == 'append':
                elem = self.visit(node.args[0])
                array = self.arrays.get(callee.parent.name)
                if not array:
                    self.arrays[callee.parent.name] = Array(elements=[])
                self.arrays[callee.parent.name].append(elem)
                index = self.lookup(callee.parent)
                if type(callee.parent) == GlobalVar:
                    code += f'Modify Global Variable At Index(A, {index}, Append To Array, {elem})'
                elif type(callee.parent) == PlayerVar:
                    player = self.visit(callee.parent.player)
                    code += f'Modify Player Variable At Index({player}, A, {index}, Append To Array, {elem})'
            elif method == 'index':
                elem = self.visit(node.args[0])
                array = self.arrays.get(callee.parent.name)
                if not array:
                    self.arrays[callee.parent.name] = Array(elements=[])
                code += str(self.arrays[callee.parent.name].index(elem))
            elif method == 'halt':
                code += 'Apply Impulse({}, Down, Multiply(0.001, 0.001), To World, Cancel Contrary Motion)'.format(self.visit(callee.parent))
            else:
                raise Errors.SyntaxError("Unknown method '{}'".format(method))
        else:
            try:
                function = self.functions[callee.name]
                if type(function) == Function:
                    assert len(function.params) == len(node.args)
                    params = [param.name for param in function.params]
                    scope = Scope(name=callee.name, parent=self.scope)
                    scope.namespace.update(dict(zip(params, node.args)))
                    children = []
                    for child in function.children:
                        child_node = child.children[0]
                        child_is_func = type(child_node) == Call and child_node.parent.name in self.functions
                        if child_is_func:
                            self.indent_level -= 1
                        children.append(self.visit(child, scope=scope))
                        if child_is_func:
                            self.indent_level += 1
                    code += (';\n' + self.tabs).join(children)
                else:
                    try:
                        result = function(self, node.args)
                        code += self.visit(result)
                    except Exception as e:
                        raise Errors.SyntaxError('Invalid parameters for function {}'.format(callee.name))
            except AssertionError:
                raise Errors.SyntaxError("{} expected {} parameters, received {}".format(callee.name, len(function.params), len(node.args)))
            except KeyError:
                raise Errors.SyntaxError("Undefined function '{}'".format(callee.name))
        return code

    def visit(self, node, scope=None):
        method_name = 'visit' + type(node).__name__
        visitor = getattr(self, method_name)
        prev_scope = self.scope
        if scope:
            self.scope = scope
        result = visitor(node)
        self.scope = prev_scope
        return result

    def visitChildren(self, node):
        code = ''
        for child in node.children:
            code += self.visit(child)
        return code

    def run(self):
        return self.visit(self.tree)