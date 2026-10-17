
package lk.sliit.codecleanliness.detection;

import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.FieldDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.ast.body.VariableDeclarator;

import lk.sliit.codecleanliness.model.FindingScope;
import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;
import lk.sliit.codecleanliness.model.RepositoryParseResult;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.regex.Pattern;

/**
 * Preliminary Java naming-convention candidate detector.
 *
 * Does not infer whether names communicate adequate
 * domain meaning. Does not prove an override, framework
 * convention, or generated identifier is incorrect.
 */
public class PoorNamingDetector {

    private static final Pattern UPPER_CAMEL =
            Pattern.compile("[A-Z][a-zA-Z0-9]*");

    private static final Pattern LOWER_CAMEL =
            Pattern.compile("[a-z][a-zA-Z0-9]*");

    private static final Pattern UPPER_SNAKE =
            Pattern.compile("[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*");

    public List<MaintainabilityFinding> detect(
            RepositoryParseResult repository,
            NamingDetectionConfig config
    ) {
        Objects.requireNonNull(repository);
        Objects.requireNonNull(config);

        List<MaintainabilityFinding> findings =
                new ArrayList<>();

        var files = repository.parsedFiles()
                .entrySet()
                .stream()
                .sorted(Comparator.comparing(
                        entry -> entry.getKey().toString()))
                .toList();

        for (Map.Entry<Path, CompilationUnit> entry : files) {

            Path file = entry.getKey()
                    .toAbsolutePath().normalize();

            CompilationUnit unit = entry.getValue();

            if (config.checkTypes()) {
                for (ClassOrInterfaceDeclaration type :
                        unit.findAll(
                                ClassOrInterfaceDeclaration.class)) {

                    if (type.getName().getRange().isEmpty()) {
                        continue;
                    }

                    String name = type.getNameAsString();

                    if (!UPPER_CAMEL.matcher(name).matches()) {
                        addFinding(
                                findings,
                                file,
                                FindingScope.CLASS,
                                qualifiedOwner(type),
                                type.getName()
                                        .getRange().orElseThrow()
                                        .begin.line,
                                "JAVA_TYPE_UPPER_CAMEL",
                                "UpperCamelCase",
                                name
                        );
                    }
                }
            }

            if (config.checkMethods()) {
                for (MethodDeclaration method :
                        unit.findAll(MethodDeclaration.class)) {

                    if (method.getName().getRange().isEmpty()) {
                        continue;
                    }

                    String name = method.getNameAsString();

                    if (!LOWER_CAMEL.matcher(name).matches()) {
                        String owner = "<unknown-type>";

                        Node parent = method.getParentNode().orElse(null);

                        while (parent != null) {
                            if (parent instanceof TypeDeclaration<?> type) {
                                owner = qualifiedOwner(type);
                                break;
                            }
                            parent = parent.getParentNode().orElse(null);
                        }

                        addFinding(
                                findings,
                                file,
                                FindingScope.METHOD,
                                owner + "."
                                        + method.getSignature().asString(),
                                method.getName()
                                        .getRange().orElseThrow()
                                        .begin.line,
                                "JAVA_METHOD_LOWER_CAMEL",
                                "lowerCamelCase",
                                name
                        );
                    }
                }
            }

            if (config.checkFields()) {
                for (FieldDeclaration field :
                        unit.findAll(FieldDeclaration.class)) {

                    // Only inspect fields whose immediate parent
                    // is a named type declaration.
                    // Fields in anonymous bodies are deferred.
                    if (!(field.getParentNode().orElse(null)
                            instanceof TypeDeclaration<?> type)) {
                        continue;
                    }

                    String owner = qualifiedOwner(type);

                    for (VariableDeclarator variable :
                            field.getVariables()) {

                        if (variable.getName().getRange().isEmpty()) {
                            continue;
                        }

                        String name = variable.getNameAsString();

                        boolean constant =
                                field.isStatic() && field.isFinal();

                        boolean valid = constant
                                ? UPPER_SNAKE.matcher(name).matches()
                                        || LOWER_CAMEL.matcher(name).matches()
                                : LOWER_CAMEL.matcher(name).matches();

                        if (valid) {
                            continue;
                        }

                        addFinding(
                                findings,
                                file,
                                FindingScope.FIELD,
                                owner + "." + name,
                                variable.getName()
                                        .getRange().orElseThrow()
                                        .begin.line,
                                constant
                                        ? "JAVA_CONSTANT_NAME"
                                        : "JAVA_FIELD_LOWER_CAMEL",
                                constant
                                        ? "UPPER_SNAKE_CASE or lowerCamelCase"
                                        : "lowerCamelCase",
                                name
                        );
                    }
                }
            }
        }

        findings.sort(
                Comparator.comparing(
                        (MaintainabilityFinding f) ->
                                f.sourceFile().toString())
                        .thenComparingInt(
                                MaintainabilityFinding::startLine)
                        .thenComparing(
                                MaintainabilityFinding::findingId)
        );

        return List.copyOf(findings);
    }

    private String qualifiedOwner(TypeDeclaration<?> type) {
        return type.getFullyQualifiedName()
                .orElseGet(() -> type.getNameAsString());
    }

    private void addFinding(
            List<MaintainabilityFinding> findings,
            Path file,
            FindingScope scope,
            String symbol,
            int line,
            String rule,
            String expected,
            String actual
    ) {
        findings.add(new MaintainabilityFinding(
                file + ":" + line + ":" + symbol + ":" + rule,
                MaintainabilityConcern.POOR_NAMING,
                scope,
                file,
                symbol,
                line,
                line,
                rule,
                "Identifier does not follow the configured "
                        + "preliminary Java naming convention.",
                Map.of(
                        "identifier", actual,
                        "expectedConvention", expected,
                        "rule", rule,
                        "measurement", "java_identifier_pattern"
                )
        ));
    }
}
