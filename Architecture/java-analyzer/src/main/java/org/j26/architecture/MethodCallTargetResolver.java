package org.j26.architecture;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.CallableDeclaration;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.Parameter;
import com.github.javaparser.ast.body.VariableDeclarator;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.TypePatternExpr;
import com.github.javaparser.ast.expr.VariableDeclarationExpr;
import com.github.javaparser.ast.expr.LambdaExpr;
import com.github.javaparser.ast.stmt.BlockStmt;
import com.github.javaparser.ast.stmt.CatchClause;
import com.github.javaparser.ast.stmt.ForEachStmt;
import com.github.javaparser.ast.stmt.ForStmt;
import com.github.javaparser.ast.stmt.TryStmt;

import java.util.List;
import java.util.Optional;

final class MethodCallTargetResolver {
    private final ProjectTypeResolver types;

    MethodCallTargetResolver(ProjectTypeResolver types) {
        this.types = types;
    }

    Optional<String> resolve(MethodCallExpr call, CompilationUnit unit, ClassOrInterfaceDeclaration owner) {
        return call.getScope().flatMap(scope -> resolveScope(scope, call, unit, owner));
    }

    private Optional<String> resolveScope(Expression scope, MethodCallExpr call,
                                          CompilationUnit unit, ClassOrInterfaceDeclaration owner) {
        if (scope.isEnclosedExpr()) {
            return resolveScope(scope.asEnclosedExpr().getInner(), call, unit, owner);
        }
        if (scope.isObjectCreationExpr()) {
            return types.resolve(scope.asObjectCreationExpr().getType(), unit, call);
        }
        if (scope.isCastExpr()) {
            return types.resolve(scope.asCastExpr().getType(), unit, call);
        }
        if (scope.isFieldAccessExpr()) {
            var access = scope.asFieldAccessExpr();
            if (access.getScope().isThisExpr() && access.getScope().asThisExpr().getTypeName().isEmpty()) {
                return field(access.getNameAsString(), owner).flatMap(binding -> bindingType(binding, unit));
            }
        }
        if (scope.isNameExpr()) {
            return binding(scope.asNameExpr().getNameAsString(), call, owner)
                    .flatMap(declaration -> bindingType(declaration, unit));
        }
        // Return types of chained calls and arbitrary member access need real symbol resolution.
        return Optional.empty();
    }

    private Optional<String> bindingType(Node binding, CompilationUnit unit) {
        if (binding instanceof Parameter parameter) {
            return types.resolve(parameter.getType(), unit, parameter);
        }
        if (binding instanceof VariableDeclarator variable) {
            if (variable.getType().isVarType()) {
                return variable.getInitializer().filter(Expression::isObjectCreationExpr)
                        .flatMap(initializer -> types.resolve(initializer.asObjectCreationExpr().getType(), unit, variable));
            }
            return types.resolve(variable.getType(), unit, variable);
        }
        return Optional.empty();
    }

    private Optional<Node> binding(String name, MethodCallExpr call, ClassOrInterfaceDeclaration owner) {
        Node branch = call;
        for (Node scope = call.getParentNode().orElse(null); scope != null && scope != owner;
             branch = scope, scope = scope.getParentNode().orElse(null)) {
            Optional<Node> found = Optional.empty();
            if (scope instanceof BlockStmt block) {
                // Equal-looking calls can be different statements. Use node identity to find this one.
                int statementIndex = block.getStatements().size() - 1;
                while (statementIndex >= 0 && block.getStatement(statementIndex) != branch) {
                    statementIndex--;
                }
                for (int i = statementIndex; i >= 0 && found.isEmpty(); i--) {
                    var statement = block.getStatement(i);
                    if (statement.isExpressionStmt() && statement.asExpressionStmt().getExpression().isVariableDeclarationExpr()) {
                        found = variables(statement.asExpressionStmt().getExpression().asVariableDeclarationExpr(), name, call);
                    }
                }
            } else if (scope instanceof LambdaExpr lambda) {
                found = parameter(lambda.getParameters(), name);
            } else if (scope instanceof CatchClause catchClause) {
                found = parameter(List.of(catchClause.getParameter()), name);
            } else if (scope instanceof CallableDeclaration<?> callable) {
                found = parameter(callable.getParameters(), name);
            } else if (scope instanceof ForEachStmt loop && contains(loop.getBody(), call)) {
                found = variables(loop.getVariable(), name, call);
            } else if (scope instanceof ForStmt loop) {
                found = loop.getInitialization().stream().filter(Expression::isVariableDeclarationExpr)
                        .map(expression -> variables(expression.asVariableDeclarationExpr(), name, call))
                        .flatMap(Optional::stream).findFirst();
            } else if (scope instanceof TryStmt tryStatement
                    && (contains(tryStatement.getTryBlock(), call)
                    || tryStatement.getResources().stream().anyMatch(resource -> contains(resource, call)))) {
                found = tryStatement.getResources().stream().filter(Expression::isVariableDeclarationExpr)
                        .map(expression -> variables(expression.asVariableDeclarationExpr(), name, call))
                        .flatMap(Optional::stream).findFirst();
            }
            // Stop even for an unknown type: a local Object or inferred lambda parameter shadows fields.
            if (found.isPresent()) {
                return found;
            }
        }

        // Pattern-variable flow scopes are not resolved yet. Avoid accidentally binding one to a field.
        for (Node scope = call.getParentNode().orElse(null); scope != null && scope != owner;
             scope = scope.getParentNode().orElse(null)) {
            if (scope instanceof CallableDeclaration<?> callable) {
                Optional<Node> pattern = callable.findAll(TypePatternExpr.class).stream()
                        .filter(candidate -> candidate.getNameAsString().equals(name)).map(node -> (Node) node).findFirst();
                return pattern.isPresent() ? pattern : field(name, owner);
            }
        }
        return field(name, owner);
    }

    private Optional<Node> variables(VariableDeclarationExpr declaration, String name, Node use) {
        return declaration.getVariables().stream().filter(variable -> variable.getNameAsString().equals(name))
                .filter(variable -> variable.getBegin().isPresent() && use.getBegin().isPresent()
                        && variable.getBegin().orElseThrow().compareTo(use.getBegin().orElseThrow()) <= 0)
                .map(variable -> (Node) variable).findFirst();
    }

    private Optional<Node> parameter(List<Parameter> parameters, String name) {
        return parameters.stream().filter(parameter -> parameter.getNameAsString().equals(name))
                .map(parameter -> (Node) parameter).findFirst();
    }

    private Optional<Node> field(String name, ClassOrInterfaceDeclaration owner) {
        return owner.getFields().stream().flatMap(field -> field.getVariables().stream())
                .filter(variable -> variable.getNameAsString().equals(name)).map(variable -> (Node) variable).findFirst();
    }

    private boolean contains(Node scope, Node use) {
        return scope == use || scope.isAncestorOf(use);
    }
}
