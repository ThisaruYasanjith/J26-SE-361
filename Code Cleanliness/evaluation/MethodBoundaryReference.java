
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.ast.*;
import com.github.javaparser.ast.body.*;
import com.github.javaparser.ast.expr.*;
import com.github.javaparser.ast.stmt.*;

import java.nio.file.*;
import java.util.*;
import java.util.stream.*;

/**
 * Milestone 29F - Method Boundary Reference Checker
 *
 * Independently implemented AST-based metric checker using
 * the same documented counting conventions as the analyzer.
 *
 * Evaluates:
 * - Method NCSS
 * - Cyclomatic complexity
 *
 * Supports Java 17 syntax.
 *
 * IMPORTANT:
 * This measures boundary-rule agreement, not independently
 * verified maintainability-smell accuracy.
 */
public class MethodBoundaryReference {

    static String q(String text) {
        return "\"" + text.replace("\"", "\"\"") + "\"";
    }

    public static void main(String[] args) throws Exception {

        if (args.length < 1) {
            System.err.println(
                "Usage: java MethodBoundaryReference <java-source-directory>"
            );
            System.exit(1);
        }

        // FIX: Enable Java 17 language features.
        ParserConfiguration configuration = new ParserConfiguration()
            .setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_17);

        StaticJavaParser.setConfiguration(configuration);

        Path base = Path.of(args[0]);

        if (!Files.isDirectory(base)) {
            throw new IllegalArgumentException(
                "Source directory does not exist: " + base
            );
        }

        System.out.println(
            "source_file,start_line,end_line,symbol,ncss,cyclomatic,parse_error"
        );

        List<Path> files;

        try (Stream<Path> paths = Files.walk(base)) {
            files = paths
                .filter(p -> p.toString().endsWith(".java"))
                .sorted()
                .toList();
        }

        for (Path file : files) {

            CompilationUnit cu;

            try {
                cu = StaticJavaParser.parse(file);
            } catch (Exception ex) {
                System.err.println(
                    "PARSE_FAIL " + file + " " + ex.getMessage()
                );
                continue;
            }

            for (MethodDeclaration m :
                    cu.findAll(MethodDeclaration.class)) {

                if (m.getBody().isEmpty() || m.getRange().isEmpty()) {
                    continue;
                }

                BlockStmt body = m.getBody().get();

                // Calculate NCSS.
                // Exclude structural blocks, empty statements,
                // and switch grouping statements.
                int ncss = 0;

                for (Statement statement :
                        body.findAll(Statement.class)) {

                    if (!(statement instanceof BlockStmt)
                            && !(statement instanceof EmptyStmt)
                            && !(statement instanceof SwitchStmt)) {

                        ncss++;
                    }
                }

                // Calculate cyclomatic complexity.
                int cyclomatic = 1;

                for (Node node : body.findAll(Node.class)) {

                    if (node instanceof IfStmt
                            || node instanceof ForStmt
                            || node instanceof ForEachStmt
                            || node instanceof WhileStmt
                            || node instanceof DoStmt
                            || node instanceof CatchClause
                            || node instanceof ConditionalExpr) {

                        cyclomatic++;
                    }

                    if (node instanceof BinaryExpr binary) {

                        if (binary.getOperator() == BinaryExpr.Operator.AND
                                || binary.getOperator() == BinaryExpr.Operator.OR) {

                            cyclomatic++;
                        }
                    }

                    if (node instanceof SwitchEntry entry
                            && !entry.getLabels().isEmpty()) {

                        cyclomatic++;
                    }
                }

                // Determine the method's enclosing class.
                List<String> owner = new ArrayList<>();

                for (Node node = m.getParentNode().orElse(null);
                        node != null;
                        node = node.getParentNode().orElse(null)) {

                    if (node instanceof TypeDeclaration<?> type) {
                        owner.add(0, type.getNameAsString());
                    }
                }

                String symbol = String.join(".", owner)
                        + "."
                        + m.getSignature().asString();

                String relativePath = base.relativize(file)
                    .toString()
                    .replace('\\', '/');

                // Output one CSV record per parsed method.
                System.out.println(
                    String.join(
                        ",",
                        q(relativePath),
                        String.valueOf(m.getRange().get().begin.line),
                        String.valueOf(m.getRange().get().end.line),
                        q(symbol),
                        String.valueOf(ncss),
                        String.valueOf(cyclomatic),
                        "0"
                    )
                );
            }
        }
    }
}
