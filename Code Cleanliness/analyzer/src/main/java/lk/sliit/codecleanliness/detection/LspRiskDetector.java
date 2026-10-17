
package lk.sliit.codecleanliness.detection;

import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.stmt.ThrowStmt;

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

/**
 * Preliminary LSP-risk detector.
 *
 * Identifies overridden methods in subclasses that
 * explicitly throw UnsupportedOperationException.
 *
 * An @Override annotation is required as evidence
 * of an intended override. This detector does not
 * infer full behavioral substitutability.
 */
public class LspRiskDetector {

    public List<MaintainabilityFinding> detect(
            RepositoryParseResult repository) {

        Objects.requireNonNull(repository);

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
                    .toAbsolutePath()
                    .normalize();

            for (ClassOrInterfaceDeclaration type :
                    entry.getValue().findAll(
                            ClassOrInterfaceDeclaration.class)) {

                if (type.isInterface()
                        || type.getExtendedTypes().isEmpty()) {
                    continue;
                }

                String owner = type.getFullyQualifiedName()
                        .orElse(type.getNameAsString());

                for (MethodDeclaration method :
                        type.getMethods()) {

                    if (!method.isAnnotationPresent("Override")
                            || method.getBody().isEmpty()
                            || method.getRange().isEmpty()) {
                        continue;
                    }

                    // Only count throws belonging directly to
                    // this method body, not nested type or
                    // lambda implementations.
                    List<ThrowStmt> suspiciousThrows =
                            method.getBody().orElseThrow()
                                    .findAll(ThrowStmt.class)
                                    .stream()
                                    .filter(statement ->
                                            statement.getExpression()
                                                    .isObjectCreationExpr())
                                    .filter(statement -> {
                                        String exceptionType =
                                                statement.getExpression()
                                                        .asObjectCreationExpr()
                                                        .getType()
                                                        .asString();

                                        return exceptionType.equals(
                                                "UnsupportedOperationException")
                                                || exceptionType.equals(
                                                "java.lang.UnsupportedOperationException");
                                    })
                                    .filter(statement -> {
                                        Node parent = statement.getParentNode().orElse(null);

                                        while (parent != null) {
                                            if (parent instanceof MethodDeclaration ownerMethod) {
                                                return ownerMethod == method;
                                            }
                                            parent = parent.getParentNode().orElse(null);
                                        }

                                        return false;
                                    })
                                    .toList();

                    if (suspiciousThrows.isEmpty()) {
                        continue;
                    }

                    int start = method.getRange()
                            .orElseThrow().begin.line;

                    int end = method.getRange()
                            .orElseThrow().end.line;

                    String symbol = owner + "."
                            + method.getSignature().asString();

                    findings.add(new MaintainabilityFinding(
                            file + ":" + start + ":" + symbol
                                    + ":LSP_RISK",
                            MaintainabilityConcern.LSP_RISK,
                            FindingScope.METHOD,
                            file,
                            symbol,
                            start,
                            end,
                            "OVERRIDE_UNSUPPORTED_OPERATION",
                            "An overriding method explicitly "
                                    + "throws UnsupportedOperationException. "
                                    + "Review whether the subclass preserves "
                                    + "the expected parent contract.",
                            Map.of(
                                    "declaringClass", owner,
                                    "methodSignature",
                                    method.getSignature().asString(),
                                    "parentTypes",
                                    type.getExtendedTypes().toString(),
                                    "unsupportedThrowCount",
                                    String.valueOf(
                                            suspiciousThrows.size()),
                                    "throwLines",
                                    suspiciousThrows.stream()
                                            .map(statement ->
                                                    statement.getBegin()
                                                            .map(position ->
                                                                    String.valueOf(
                                                                            position.line))
                                                            .orElse("unknown"))
                                            .sorted()
                                            .toList()
                                            .toString(),
                                    "measurement",
                                    "preliminary_override_exception_pattern"
                            )
                    ));
                }
            }
        }

        findings.sort(
                Comparator.comparing(
                        (MaintainabilityFinding finding) ->
                                finding.sourceFile().toString())
                        .thenComparingInt(
                                MaintainabilityFinding::startLine)
                        .thenComparing(
                                MaintainabilityFinding::findingId)
        );

        return List.copyOf(findings);
    }
}
