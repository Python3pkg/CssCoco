from coco.ast.ast import *
from coco.syntax.cocoParser import *
from coco.syntax.cocoVisitor import cocoVisitor
from antlr4.tree.Tree import *


class CocoCustomVisitor(cocoVisitor):

    identifiers = set()

    def visitStylesheet(self, ctx):
        contexts = []
        for contextCtx in ctx.children:
            contexts.append(self.visitContext(contextCtx))
        return ConventionSet(contexts)

    def visitContext(self, context):
        conventions = self.get_conventions(context)
        title = context.name.text
        if title == 'Semantic':
            return SemanticContext(conventions, [])
        if title == 'Whitespace':
            return WhitespaceContext(conventions, [])
        raise NotImplementedError()

    def get_conventions(self, context):
        result = []
        # Antlr does not allow labels here, so use weird indexes
        for i in range(2, len(context.children)-1):
            convention = self.visitDeclaration(context.children[i])
            result.append(convention)
        return result

    def visitDeclaration(self, context):
        # A declaration is currently only convention
        return self.visitConvention(context.children[0])

    def visitConvention(self, context):
        message = self.visitMessage(context)
        target = self.visitPattern(context.target)

        if self.is_forbid_convention(context):
            return ForbidConvention(target, message)

        if self.is_find_require_convention(context):
            self.push_identifiers(target)
            requirement = self.visitLogic_expr(context.requirement)
            self.pop_identifiers()
            return FindRequireConvention(target, message=message, constraint=requirement)

        raise NotImplementedError('Unknown convention type')

    def visit_require_convention(self, context):
        succeeded, target = self.interpolate_target(context.requirement)
        if not succeeded:
            raise ValueError('Invalid convention target. Consider breaking the convention to simpler patterns')
        message = self.visitMessage(context.msg)

        self.push_identifiers(target)
        requirement = self.visitAttr_expression(context.requirement)
        self.pop_identifiers()

        return FindRequireConvention(target, message=message, constraint=requirement)

    def interpolate_target(self, context):
        if context.operator:
            operator = context.operator.text
            wrappers = []
            if operator == 'after' or operator == 'before':
                right = self.visit_whitespace_argument(context.right, 'a1')
                wrappers.append(right)
            if operator == 'between':
                first = self.visit_whitespace_argument(context.first, 'a1')
                second = self.visit_whitespace_argument(context.second, 'a2')

                wrappers.append(first)
                wrappers.append(second)
            return True, SequencePatternExpr(wrappers)
        return False, None

    def visit_whitespace_argument(self, context, identifier):
        if context.abstract:
            return self.visit_abstract_node_decl(context.abstract, identifier)
        # if context.call:
        #     return self.visitCall_expression(context.call)
        if context.string_:
            raise NotImplementedError()
        raise ValueError('Unknown whitespace argument')

    def push_identifiers(self, target):
        for wrapper in target.all_descs:
            if wrapper.has_identifier():
                self.identifiers.add(wrapper.identifier)

    def pop_identifiers(self):
        self.identifiers = set()

    def is_forbid_convention(self, ctx):
        return ctx.children[0].symbol.text == 'forbid'

    def is_find_require_convention(self, ctx):
        return ctx.children[0].symbol.text == 'find' and \
               ctx.children[2].symbol.text == 'require'

    def is_require_convention(self, ctx):
        return ctx.children[0].symbol.text == 'require'

    def visitMessage(self, context):
        return self.unescape_quotes(context.message.text)

    def visitPattern(self, ctx):
        wrappers = self.get_node_declarations(ctx)
        relations, root = self.build_relations(ctx, wrappers)
        return PatternExpr(wrappers[root], wrappers, relations)

    def get_node_declarations(self, context):
        result = []
        for i in range(0, len(context.children), 2):
            wrapper = self.visitNode_declaration(context.children[i])
            result.append(wrapper)
        return result

    def build_relations(self, context, wrappers):
        relations = Relations()
        if self.is_single_node_pattern(context):
            return relations, 0
        title = context.relation.text
        root = -1
        for i in range(1, len(wrappers)):
            if title == 'in':
                relations.register_relation(wrappers[i], IsAncestorOfRelation(wrappers[i-1]))
            elif title == 'next-to':
                relations.register_relation(wrappers[i-1], IsPreviousSiblingOfRelation(wrappers[i]))
                root = 0
        return relations, root

    def is_single_node_pattern(self, context):
        return len(context.children) == 1

    def visitNode_declaration(self, context):
        if context.variable and context.node:
            return self.visit_semantic_node_id(context.node, context.variable.text)
        if context.node:
            return self.visitSemantic_node(context.node)
        raise ValueError('Unknown node declaration')

    def visit_semantic_node_id(self, context, variable):
        node_descriptor = self.get_node_descriptor(context.node_type)
        if not context.constraint:
            return NodeExprWrapperWithId(node_descriptor, variable)
        constraint = self.visitLogic_expr(context.constraint)
        return NodeExprWrapperWithId(node_descriptor, variable, constraint)

    def visitSemantic_node(self, context):
        node_descriptor = self.get_node_descriptor(context.node_type)
        if not context.constraint:
            return NodeExprWrapper(node_descriptor)
        constraint = self.visitLogic_expr(context.constraint)
        return NodeExprWrapper(node_descriptor, constraint)

    def visitLogic_expr(self, context):
        if context.parenthesis:
            return self.visitLogic_expr(self.parenthesis)

        if context.primary_type:
            return self.visitType_expr(context.primary_type)

        if context.primary_call:
            return self.visitCalls_expr(context.primary_call)

        operator = context.operator.text
        if operator == 'is':
            operand = self.visitCalls_expr(context.operand)
            node_type = NodeTypeExpr(context.node_type.text)
            return IsExpr(operand, node_type)
        if operator == 'not':
            operand = self.visitLogic_expr(context.operand)
            return NotExpr(operand)
        left = self.visitLogic_expr(context.left)
        right = self.visitLogic_expr(context.right)
        if operator == 'and':
            return AndExpr(left, right)
        if operator == 'or':
            return OrExpr(left, right)

        raise ValueError('Unknown logic expression')

    def visitType_expr(self, context):
        variation = self.visitWhitespace_variation(context.variation)
        operand = self.get_type_expr_right(context.variable, context.operand)
        operator = context.operator.text
        if operator == 'before':
            return BeforeExpr(operand, variation)
        if operator == 'after':
            return AfterExpr(operand, variation)
        if operator == 'between':
            second_operand = self.get_type_expr_right(context.second_variable, context.second_operand)
            return BetweenExpr(operand, variation, second_operand)
        raise ValueError('Unknown type expression')

    def get_type_expr_right(self, variable, operand):
        if variable:
            return VariableExpr(variable.text)
        if operand:
            return self.visitSemantic_node(operand)
        raise ValueError('Unknown type expr right')

    def visitWhitespace_variation(self, context):
        sequences = []
        for i in range(0, len(context.children), 2):
            descriptor = self.visitWhitespace_node(context.children[i])
            sequences.append(SequencePatternExpr([descriptor]))
        return WhitespaceVariation(sequences)

    def visitWhitespace_node(self, context):
        node_descriptor = self.get_ws_node_descriptor(context.node_type.text)
        if context.quantifier:
            repeater = self.visitRepeater(context.quantifier)
            return NodeSequenceExprWrapper(node_descriptor, repeater)
        return node_descriptor

    def visitRepeater(self, context):
        lower = -1
        upper = -1
        if context.exact:
            limit = int(context.exact.text)
            lower = limit
            upper = limit
        if context.lower:
            lower = int(context.lower.text)
        if context.upper:
            upper = int(context.upper.text)
        return Repeater(lower=lower, upper=upper)

    def visitCalls_expr(self, context):
        if context.primary_int:
            return DecimalExpr(int(context.primary_int.text))

        if context.primary_str:
            return StringExpr(self.unescape_quotes(context.primary_str.text))

        if context.primary_list:
            return self.visitList_(context.primary_list)

        if context.primary_call:
            return self.visitCall_expression(context.primary_call)

        operator = context.operator.text
        if operator == '-':
            operand = self.visitCalls_expr(context.operand)
            return UnaryMinusExpr(operand)

        left = self.visitCalls_expr(context.left)
        right = self.visitCalls_expr(context.right)

        if operator == '==':
            return EqualsExpr(left, right)
        if operator == '!=':
            return NotEqualsExpr(left, right)
        if operator == '<':
            return LessThanExpr(left, right)
        if operator == '>':
            return GreaterThanExpr(left, right)
        if operator == '<=':
            return LessThanOrEqExpr(left, right)
        if operator == '>=':
            return GreaterThanOrEqExpr(left, right)

        if operator == 'in':
            return InExpr(left, right)
        if operator == 'not in':
            raise NotImplementedError()
        if operator == 'match':
            return MatchExpr(left, right)
        if operator == 'not match':
            return NotExpr(MatchExpr(left, right))



    # def visitNode(self, ctx):
    #     if ctx.abstract and ctx.decl:
    #         return self.visit_abstract_node_decl(ctx.abstract, ctx.decl.text)
    #     if ctx.abstract:
    #         return self.visitAbstract_node(ctx.abstract)
    #     if ctx.parse:
    #         return self.visitParse_node(ctx.parse)
    #     raise ValueError('Unknown node')
    #
    # def visitAbstract_node(self, ctx):
    #     node_descriptor, attr_expression = self.get_type_and_attr_expr(ctx)
    #     return NodeExprWrapper(node_descriptor, attr_expr=attr_expression)
    #
    # def visit_abstract_node_decl(self, ctx, identifier):
    #     node_descriptor, attr_expression = self.get_type_and_attr_expr(ctx)
    #     return NodeExprWrapperWithId(node_descriptor, identifier, attr_expr=attr_expression)

    def get_type_and_attr_expr(self, ctx):
        node_descriptor = self.get_node_descriptor(ctx.node_type)
        if not ctx.constraint:
            return node_descriptor, None
        attr_expression = self.visitAttr_expression(ctx.constraint)
        return node_descriptor, attr_expression

    def visitParse_node(self, ctx):
        if ctx.parenthesis:
            return self.visitParse_node(ctx.parenthesis)
        if ctx.left:
            left = self.visit(ctx.left)
            right = self.visit(ctx.right)
            return OrExpr(left, right)
        if ctx.primary:
            node_descriptor = self.get_node_descriptor(ctx)
            repeater = Repeater.DEFAULT
            if self.parse_node_has_constraint(ctx):
                repeater = self.get_parse_node_constraint(ctx)
            return NodeSequenceExprWrapper(node_descriptor, repeater)

    def parse_node_has_constraint(self, ctx):
        return ctx.lower or ctx.upper or ctx.exact

    def get_parse_node_constraint(self, ctx):
        if ctx.exact:
            exact = int(ctx.exact)
            return Repeater(exact, exact)
        if ctx.lower and ctx.upper:
            lower = int(ctx.lower)
            upper = int(ctx.upper)
            return Repeater(lower, upper)
        if ctx.lower:
            lower = int(ctx.lower)
            return Repeater(lower=lower)
        if ctx.upper:
            upper = int(ctx.upper)
            return Repeater(upper=upper)
        raise ValueError('Unknown parse node constraint')

    def visitCall_expression(self, ctx):
        identifier = ctx.call.text
        if identifier in self.identifiers:
            return VariableExpr(identifier)
        if identifier == 'lowercase':
            return StringExpr('^[^A-Z]+$')
        if identifier == 'shorten':
            return StringExpr('(?P<gr1>[0-9a-f])(?P=gr1)(?P<gr2>[0-9a-f])(?P=gr2)(?P<gr3>[0-9a-f])(?P=gr3)')

        operand = VariableExpr.DEFAULT
        if ctx.operand:
            operand = self.visitCall_expression(ctx.operand)

        argument = self.visit_argument(ctx)
        if argument:
            if identifier == 'contains-all':
                return ContainsAllExpr(operand, argument)
            return MethodExpr(operand, ctx.call.text, argument)
        return PropertyExpr(operand, ctx.call.text)

    def visit_argument(self, context):
        if context.argument:
            return self.visitCalls_expr(context.argument)
        if context.abstract:
            return self.visitSemantic_node(context.abstract)
        return None

    def visitList_(self, ctx):
        result = []
        for child in ctx.children:
            if type(child) is cocoParser.List_elementContext:
                element = self.visitList_element(child)
                result.append(element)
        return ListExpr(result)

    def visitList_element(self, ctx):
        if ctx.element_id is not None:
            raise NotImplementedError()
        if ctx.element_int is not None:
            return int(ctx.element_int.text)
        if ctx.element_str is not None:
            return StringExpr(self.unescape_quotes(ctx.element_str.text))
        if ctx.element_desc is not None:
            return self.visitSemantic_node(ctx.element_desc)
        raise ValueError('Unknown list element')

    def visitType_expression(self, ctx):
        if ctx.parenthesis:
            return self.visitType_expression(ctx.parenthesis)
        if ctx.operand:
            operand = self.visitType_expression(ctx.operand)
            return NotExpr(operand)
        if ctx.left:
            left = self.visitType_expression(ctx.left)
            right = self.visitType_expression(ctx.right)
            if ctx.operator.text == 'and':
                return AndExpr(left, right)
            if ctx.operator.text == 'or':
                return OrExpr(left, right)
        if ctx.primary:
            return NodeTypeExpr(ctx.primary.text)
        raise ValueError('Unknown type expression')


    def get_node_descriptor(self, ctx):
        lambda_string = self.get_type_expression_string(ctx)
        lambda_ = eval('lambda n: ' + lambda_string)
        return NodeDescriptor(func=lambda_)

    def get_ws_node_descriptor(self, text):
        string = ''.join(['lambda n: \'', text, '\' in n.search_labels'])
        lambda_ = eval(string)
        return NodeDescriptor(func=lambda_)

    def get_type_expression_string(self, ctx):
        if ctx.parenthesis:
            return self.get_type_expression_string(ctx.children[1])

        if ctx.left:
            left = self.get_type_expression_string(ctx.left)
            right = self.get_type_expression_string(ctx.right)
            return ''.join([left, ' ', ctx.operator.text, ' ', right])

        if ctx.primary:
            return ''.join(['\'', ctx.primary.text, '\' in n.search_labels'])

        if ctx.operand:
            return 'not (' + self.get_type_expression_string(ctx.operand) + ')'

        raise ValueError('Unknown type expression')

    def unescape_quotes(self, string):
        if len(string) < 2:
            return string
        result = string[1:-1]
        return result.replace('\\\'', '\'')