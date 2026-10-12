package lk.sliit.codecleanliness;

import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.BinaryExpr;
import com.github.javaparser.ast.expr.ConditionalExpr;
import com.github.javaparser.ast.stmt.*;

import java.util.List;
import java.util.stream.Collectors;

public class MethodMetricsCalculator {

    public MethodMetrics calculate(MethodDeclaration method) {

        if (method.getBody().isEmpty()) {
            return new MethodMetrics(
                    method.getNameAsString(),
                    method.getBegin().map(p -> p.line).orElse(-1),
                    0,
                    0
            );
        }

        BlockStmt body = method.getBody().orElseThrow();

        int ncss = calculateNcss(body);
        int complexity = calculateCyclomaticComplexity(body);

        return new MethodMetrics(
                method.getNameAsString(),
                method.getBegin().map(p -> p.line).orElse(-1),
                ncss,
                complexity
        );
    }

    private int calculateNcss(BlockStmt body) {

        List<Statement> statements =
                body.findAll(Statement.class);

        int count = 0;

        for (Statement statement : statements) {

            // Structural blocks and empty statements
            // do not independently count as NCSS.
            if (statement instanceof BlockStmt ||
                    statement instanceof EmptyStmt) {
                continue;
            }

            // A switch entry is a structural grouping,
            // rather than a separate executable statement.
            if (statement instanceof SwitchStmt) {
                    continue;
            }

            count++;
        }

        return count;
    }

    private int calculateCyclomaticComplexity(BlockStmt body) {

        int complexity = 1;

        for (Node node : body.findAll(Node.class)) {

            if (node instanceof IfStmt ||
                    node instanceof ForStmt ||
                    node instanceof ForEachStmt ||
                    node instanceof WhileStmt ||
                    node instanceof DoStmt ||
                    node instanceof CatchClause ||
                    node instanceof ConditionalExpr) {

                complexity++;
            }

            if (node instanceof BinaryExpr binary) {

                if (binary.getOperator() ==
                        BinaryExpr.Operator.AND ||
                        binary.getOperator() ==
                        BinaryExpr.Operator.OR) {

                    complexity++;
                }
            }

            if (node instanceof SwitchEntry entry &&
                    !entry.getLabels().isEmpty()) {

                complexity++;
            }
        }

        return complexity;
    }
}