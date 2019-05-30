from string import capwords
from AST import *
from OWScriptVisitor import OWScriptVisitor
class ASTBuilder(OWScriptVisitor):
    """Builds an AST from a parse tree generated by ANTLR."""
    def visitScript(self, ctx):
        script = Script()
        for child in ctx.children:
            x = self.visit(child)
            if type(x) in (Function, Call):
                script.functions.append(x)
            elif type(x) == Ruleset:
                script.rulesets.append(x)
        return script

    def visitRuleset(self, ctx):
        ruleset = Ruleset()
        for child in ctx.children:
            ruleset.rules.append(self.visit(child))
        return ruleset

    def visitRuledef(self, ctx):
        rule = Rule()
        rule.rulename = self.visit(ctx.rulename())
        for rulebody in ctx.rulebody():
            rule.rulebody.append(self.visit(rulebody))
        return rule

    def visitRulename(self, ctx):
        return ctx.STRING()

    def visitRulebody(self, ctx):
        if ctx.RULEBLOCK():
            ruleblock = Ruleblock(type_=ctx.RULEBLOCK().getText())
            ruleblock.block = self.visit(ctx.ruleblock())
            return ruleblock
        return self.visit(ctx.call())

    def visitBlock(self, ctx):
        block = Block()
        for line in ctx.line():
            x = self.visit(line)
            if x:
                block.lines.append(x)
        return block

    def visitAdd(self, ctx):
        left = self.visit(ctx.children[0])
        right = self.visit(ctx.children[2])
        return BinaryOp(left=left, op='+', right=right)

    def visitSub(self, ctx):
        left = self.visit(ctx.children[0])
        right = self.visit(ctx.children[2])
        return BinaryOp(left=left, op='-', right=right)

    def visitMul(self, ctx):
        left = self.visit(ctx.children[0])
        right = self.visit(ctx.children[2])
        return BinaryOp(left=left, op='*', right=right)

    def visitDiv(self, ctx):
        left = self.visit(ctx.children[0])
        right = self.visit(ctx.children[2])
        return BinaryOp(left=left, op='/', right=right)

    def visitPow(self, ctx):
        left = self.visit(ctx.children[0])
        right = self.visit(ctx.children[2])
        return BinaryOp(left=left, op='^', right=right)

    def visitMod(self, ctx):
        left = self.visit(ctx.children[0])
        right = self.visit(ctx.children[2])
        return BinaryOp(left=left, op='%', right=right)

    def visitParens(self, ctx):
        return self.visit(ctx.children[1])

    def visitFuncdef(self, ctx):
        funcname = ctx.NAME().getText()
        funcbody = self.visit(ctx.funcbody())
        return Function(name=funcname, body=funcbody)

    def visitFuncbody(self, ctx):
        return self.visit(ctx.ruleset() or ctx.ruledef() or ctx.rulebody() or ctx.block())

    def visitAssign(self, ctx):
        assign = Assign()
        assign.left = self.visit(ctx.children[0])
        assign.op = ctx.ASSIGN().getText()
        assign.right = self.visit(ctx.expr())
        return assign

    def visitCompare(self, ctx):
        if len(ctx.arith()) == 2:
            compare = Compare()
            compare.left = self.visit(ctx.arith()[0])
            compare.op = ctx.COMPARE().getText()
            compare.right = self.visit(ctx.arith()[1])
            return compare
        return self.visit(ctx.arith()[0])

    def visitValue(self, ctx):
        value = Value(value=capwords(ctx.VALUE().getText()))
        for child in ctx.children:
            x = self.visit(child)
            if x:
                if type(x) == Block and not x.lines:
                    continue
                value.args.append(x)
        return value

    def visitAction(self, ctx):
        action = Action(value=capwords(ctx.ACTION().getText()))
        for child in ctx.children:
            x = self.visit(child)
            if x:
                if type(x) == Block and not x.lines:
                    continue
                action.args.append(x)
        return action

    def visitAfter_line(self, ctx):
        if len(ctx.children) == 3:
            return self.visit(ctx.children[1])
        return self.visit(ctx.children[0])

    def visitArg_list(self, ctx):
        arg_list = Block()
        for child in ctx.children:
            x = self.visit(child)
            if x:
                arg_list.lines.append(x)
        return arg_list

    def visitArray(self, ctx):
        array = Array()
        if len(ctx.children) == 3:
            array.elements = self.visit(ctx.children[1]).lines
        return array

    def visitItem(self, ctx):
        array = self.visit(ctx.children[0])
        index = self.visit(ctx.children[2])
        return Item(array=array, index=index)

    def visitName(self, ctx):
        text = ctx.NAME().getText()
        if text.startswith('Wait'):
            action = Action(value='Wait')
            action.args.append(Time(value=text.lstrip('Wait ')))
            return action
        return Name(value=ctx.NAME().getText())

    def visitConst(self, ctx):
        return Name(value=ctx.getText())

    def visitNumeral(self, ctx):
        return Numeral(value=ctx.num_const.text)

    def visitTime(self, ctx):
        return Time(value=ctx.getText())

    def visitVector(self, ctx):
        vector = Value(value='Vector')
        for child in ctx.children:
            x = self.visit(child)
            if x:
                if type(x) == Block and not x.lines:
                    continue
                vector.args.append(x)
        return vector

    def visitGlobal_var(self, ctx):
        gvar = GlobalVar(name=ctx.scope.text)
        return gvar

    def visitPlayer_var(self, ctx):
        pvar = PlayerVar(name=ctx.scope.text)
        if len(ctx.children) == 3:
            pvar.player = self.visit(ctx.children[-1])
        return pvar

    def visitCall(self, ctx):
        return Call(func=ctx.NAME().getText())

    def run(self, parse_tree):
        return self.visit(parse_tree)