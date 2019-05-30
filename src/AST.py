class AST:
    pass

class Script(AST):
    def __init__(self, functions=None, rulesets=None):
        self.functions = functions or []
        self.rulesets = rulesets or []

    def __repr__(self):
        return f'Functions: {self.functions}\nRulesets: {self.rulesets}'

class Ruleset(AST):
    def __init__(self, rules=None):
        self.rules = rules or []

    def __repr__(self):
        rules = '\n'.join(map(repr, self.rules))
        return f'{rules}'

class Rule(AST):
    def __init__(self, rulename='', rulebody=None):
        self.rulename = rulename
        self.rulebody = rulebody or []

    def __repr__(self):
        ruleblocks = '\n\t'.join(map(repr, self.rulebody))
        return f'Rule {self.rulename}\n\t{ruleblocks}\n'

class Ruleblock(AST):
    def __init__(self, type_, block=None):
        self.type = type_
        self.block = block

    def __repr__(self):
        return f'{self.type}: {self.block}'

class Block(AST):
    def __init__(self, lines=None):
        self.lines = lines or []

    def __repr__(self):
        return f'{self.lines}'

class BinaryOp(AST):
    def __init__(self, left=None, op=None, right=None):
        self.left = left
        self.op = op
        self.right = right

    def __repr__(self):
        return f'{self.left} {self.op} {self.right}'

class Assign(BinaryOp):
    pass

class Compare(BinaryOp):
    pass

class Type(AST):
    def __init__(self, value, args=None):
        self.value = value
        self.args = args or []

    def __repr__(self):
        if self.args:
            return f'{self.value}: {self.args}'
        return f'{self.value}'

class Value(Type):
    pass

class Action(Type):
    pass

class Constant(AST):
    def __init__(self, value):
        self.value = value
        self.name = value

    def __repr__(self):
        return f'{self.value}'

class Numeral(Constant):
    pass

class Name(Constant):
    pass

class Time(Constant):
    pass

class GlobalVar(AST):
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f'{self.name}'

class PlayerVar(AST):
    def __init__(self, name, player=None):
        self.name = name
        self.player = player or 'Event Player'

    def __repr__(self):
        return f'{self.name}@{self.player}'

class Array(AST):
    def __init__(self, elements=None):
        self.elements = elements or []

    def __repr__(self):
        return f'{self.elements}'

class Item(AST):
    def __init__(self, array, index):
        self.array = array
        self.index = index

    def __repr__(self):
        return f'{self.array}[{self.index}]'

class Function(AST):
    def __init__(self, name, body):
        self.name = name
        self.body = body

    def __repr__(self):
        return f'%{self.name}'

class Call(AST):
    def __init__(self, func):
        self.func = func

    def __repr__(self):
        return f'%{self.func}()'