from collections import defaultdict
from itertools import chain, count
from string import capwords

try:
    from . import Errors
    from .AST import *
except ImportError:
    from AST import *

def flatten(l):
    l = list(l)
    while l:
        while l and isinstance(l[0], list):
            l[0:1] = l[0]
        if l: yield l.pop(0)

class Scope:
    def __init__(self, name, parent=None, namespace=None, level=0):
        self.name = name
        self.parent = parent
        self.namespace = namespace or {}
        self.level = 0

    def get(self, name, default=None):
        value = self.namespace.get(name, default)
        if value is not None:
            return value
        if self.parent:
            return self.parent.get(name, default)

    def assign(self, name, value, index=None):
        self.namespace[name] = Variable(value=value, index=index)

    def __repr__(self):
        return f"<Scope '{self.name}'[{self.level}]>"

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
        self.global_index = count()
        self.player_index = count()
        self.line = 0
        self.scope = Scope(name='global')

    @property
    def tabs(self):
        return ' ' * self.indent_size * self.indent_level

    def visitScript(self, node):
        code = r'rule("Generated by https://github.com/adapap/OWScript") { Event { Ongoing - Global; }}' + '\n'
        return (code + self.visitChildren(node)).rstrip('\n')

    def visitRule(self, node):
        code = ''
        if node.disabled:
            code += 'disabled '
        code += 'rule('
        code += node.name
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
        name = node.name.title()
        code = name
        Errors.POS = node.pos
        try:
            assert len(node.args) == len(node.children)
        except AssertionError:
            raise Errors.SyntaxError('\'{}\' requires {} parameters ({}), received {}'.format(
                name, len(node.args), ', '.join(map(lambda arg: arg.__name__, node.args)), len(node.children))
            )
        for index, types in enumerate(zip(node.args, node.children)):
            arg, child = types
            Errors.POS = child.pos
            if arg is None:
                continue
            extends = arg._extends if hasattr(arg, '_extends') else []
            values = list(flatten(arg.get_values()))
            if 'ANY' in values:
                continue
            value = self.visit(child).upper()
            if value not in values:
                raise Errors.InvalidParameter('\'{}\' expected type {} for parameter {}, received {}'.format(name, arg.__name__, index + 1, child.__class__.__name__))
        children = [self.visit(child) for child in node.children]
        code += '(' + ', '.join(children) + ')'
        return code

    def visitConstant(self, node):
        return node.name.title()

    def visitCompare(self, node):
        if node.op.lower() == 'in':
            return 'Array Contains(' + self.visit(node.right) + ', ' + self.visit(node.left) + ')'
        elif node.op.lower() == 'not in':
            return 'Not(Array Contains(' + self.visit(node.right) + ', ' + self.visit(node.left) + '))'
        return 'Compare(' + self.visit(node.left) + f', {node.op}, ' + self.visit(node.right) + ')'

    def visitAssign(self, node):
        code = ''
        value = {
            '+=': BinaryOp(left=node.left, op='+', right=node.right),
            '-=': BinaryOp(left=node.left, op='-', right=node.right),
            '*=': BinaryOp(left=node.left, op='*', right=node.right),
            '/=': BinaryOp(left=node.left, op='/', right=node.right),
            '^=': BinaryOp(left=node.left, op='^', right=node.right),
            '%=': BinaryOp(left=node.left, op='%', right=node.right)
        }.get(node.op, node.right)
        # Configure value
        if type(node.right) == OWID:
            pass
        # Define variables
        if type(node.left) == GlobalVar:
            name = node.left.name
            var = self.scope.get(name)
            index = var.index if var else next(self.global_index)
            self.scope.assign(name=name, value=value, index=index)
        elif type(node.left) == PlayerVar:
            name = node.left.name
            var = self.scope.get(name)
            index = var.index if var else next(self.player_index)
            player = node.left.player
            self.scope.assign(name=name, value=value, index=index)
        elif type(node.left) == Item:
            parent = node.left.parent
            name = parent.name
            var = self.scope.get(name)
            try:
                index = int(self.visit(node.left.index))
                var.value[index] = value
                value = var.value
            except ValueError:
                # create temp variable, adjust and rebuild array
                # index = self.visit(node.left.index)
                Errors.POS = node.pos
                raise Errors.NotImplementedError('Array assignment only supports literal indices')
            player = self.visit(parent.player) if type(parent) == PlayerVar else None
            self.scope.assign(name=name, value=value, index=index)
        else:
            raise Errors.NotImplementedError('Assign to {} not implemented'.format(type(node.left)))
        if name.startswith('gvar_'):
            code += 'Set Global Variable At Index(A, {}, {})'.format(index, self.visit(value))
        elif name.startswith('pvar_'):
            code += 'Set Player Variable At Index({}, A, {}, {})'.format(self.visit(player), index, self.visit(value))
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
            if type(node.false_block) == If:
                skip_false += self.tabs + 'Skip({});\n'
                false_code += self.tabs + self.visit(node.false_block)
            else:
                skip_false += self.tabs + 'Skip({});\n'
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
        if type(node.left) == Number and type(node.right) == Number:
            func = {
                '+': lambda a, b: a + b,
                '-': lambda a, b: a - b,
                '*': lambda a, b: a * b,
                '/': lambda a, b: a / b,
                '^': lambda a, b: a ** b,
                '%': lambda a, b: a % b
            }.get(node.op, None)
            if func:
                try:
                    result = func(node.left, node.right)
                    return self.visit(Number(value='{}'.format(result)))
                except ZeroDivisionError:
                    return self.visit(Number(value='0'))
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
        elif node.op == '+':
            code = 'Abs(' + self.visit(node.right) + ')'
        elif node.op == 'not':
            code = 'Not(' + self.visit(node.right) + ')'
        return code

    def visitGlobalVar(self, node):
        name = node.name
        var = self.scope.get(name)
        if not var:
            Errors.POS = node.pos
            raise Errors.NameError('\'{}\' is undefined'.format(node.name[5:]))
        elif type(var.value) in (Number, Constant, String):
            return self.visit(var.value)
        node = 'Value In Array(Global Variable(A), {})'.format(var.index)
        return node

    def visitPlayerVar(self, node):
        name = node.name
        var = self.scope.get(name)
        if not var:
            Errors.POS = node.pos
            raise Errors.NameError('pvar \'{}\' is undefined'.format(node.name[5:]))
        elif type(var.value) in (Number, Constant, String):
            return self.visit(var.value)
        node = 'Value In Array(Player Variable({}, A), {})'.format(self.visit(node.player), var.index)
        return node

    def visitString(self, node):
        code = 'String("' + node.value.title() + '", '
        children = ', '.join(self.visit(child) for child in node.children)
        code += children + ')'
        return code

    def visitNumber(self, node):
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
            elements = []
            for elem in node.elements:
                if type(elem) == String:
                    elements.append(Constant(name='Null'))
                else:
                    elements.append(elem)
            num_elems = len(elements)
            if num_elems == 0:
                return 'Empty Array'
            code = 'Append To Array(' * num_elems
            code += 'Empty Array, ' + '), '.join(self.visit(elem) for elem in elements) + ')'
        return code

    def visitItem(self, node):
        if type(node.index) == Number and type(node.parent) in (GlobalVar, PlayerVar):
            try:
                index = int(node.index.value)
                var = self.scope.get(node.parent.name)
                if not var:
                    Errors.POS = node.parent.pos
                    raise Errors.NameError('{}\'{}\' is undefined'.format('pvar ' if type(node.parent) == PlayerVar else '', node.parent.name[5:]))
                try:
                    item = var.value[index]
                except IndexError:
                    item = Number(value='0')
                return self.visit(item)
            except ValueError:
                pass
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
            'team': 'Team Of({})',
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
                Errors.POS = callee.pos
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
            Errors.POS = callee.pos
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
        code = self.visit(self.tree)
        return code