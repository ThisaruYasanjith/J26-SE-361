
package lk.sliit.codecleanliness.detection;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.InstanceOfExpr;
import com.github.javaparser.ast.type.ClassOrInterfaceType;

import lk.sliit.codecleanliness.model.FindingScope;
import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;
import lk.sliit.codecleanliness.model.RepositoryParseResult;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/**
 * Preliminary Open/Closed Principle risk detector.
 *
 * Identifies methods that repeatedly branch on the same
 * expression's concrete type using instanceof.
 *
 * Evidence requires at least three distinct concrete
 * types declared in the analyzed repository.
 *
 * This is a maintainability review candidate, not proof
 * of an OCP violation.
 */
public class OcpRiskDetector {

    private static final int MIN_CONCRETE_TYPES = 3;

    public List<MaintainabilityFinding> detect(
            RepositoryParseResult repository) {

        Objects.requireNonNull(repository);

        Map<String, ClassOrInterfaceDeclaration> classes =
                indexConcreteClasses(repository);

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

            for (ClassOrInterfaceDeclaration owner :
                    unit.findAll(ClassOrInterfaceDeclaration.class)) {

                if (owner.isInterface()) {
                    continue;
                }

                String ownerName = owner.getFullyQualifiedName()
                        .orElse(owner.getNameAsString());

                for (MethodDeclaration method : owner.getMethods()) {

                    if (method.getBody().isEmpty()
                            || method.getRange().isEmpty()) {
                        continue;
                    }

                    // Expression text -> distinct resolved concrete types
                    Map<String, Set<String>> checks =
                            new TreeMap<>();

                    for (InstanceOfExpr check :
                            method.getBody().orElseThrow()
                                    .findAll(InstanceOfExpr.class)) {

                        if (!belongsToMethod(check, method)) {
                            continue;
                        }

                        if (!check.getType()
                                .isClassOrInterfaceType()) {
                            continue;
                        }

                        ClassOrInterfaceType checkedType =
                                check.getType()
                                        .asClassOrInterfaceType();

                        String concreteName =
                                resolveRepositoryClass(
                                        checkedType,
                                        unit,
                                        classes
                                );

                        if (concreteName == null) {
                            continue;
                        }

                        String selector = check.getExpression()
                                .toString();

                        checks.computeIfAbsent(
                                selector,
                                ignored -> new TreeSet<>()
                        ).add(concreteName);
                    }

                    for (Map.Entry<String, Set<String>> group :
                            checks.entrySet()) {

                        if (group.getValue().size()
                                < MIN_CONCRETE_TYPES) {
                            continue;
                        }

                        int start = method.getRange()
                                .orElseThrow().begin.line;

                        int end = method.getRange()
                                .orElseThrow().end.line;

                        String symbol = ownerName + "."
                                + method.getSignature().asString();

                        findings.add(new MaintainabilityFinding(
                                file + ":" + start + ":"
                                        + symbol + ":OCP_RISK:"
                                        + group.getKey(),
                                MaintainabilityConcern.OCP_RISK,
                                FindingScope.METHOD,
                                file,
                                symbol,
                                start,
                                end,
                                "REPEATED_CONCRETE_TYPE_CHECKS",
                                "A method repeatedly checks the same "
                                        + "expression against several "
                                        + "repository-known concrete types. "
                                        + "Review whether extensions would "
                                        + "require modifying this method.",
                                Map.of(
                                        "declaringClass", ownerName,
                                        "methodSignature",
                                        method.getSignature().asString(),
                                        "checkedExpression",
                                        group.getKey(),
                                        "concreteTypes",
                                        String.join(", ", group.getValue()),
                                        "distinctTypeCount",
                                        String.valueOf(
                                                group.getValue().size()),
                                        "configuredMinTypes",
                                        String.valueOf(MIN_CONCRETE_TYPES),
                                        "measurement",
                                        "repeated_concrete_instanceof_checks"
                                )
                        ));
                    }
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

    private boolean belongsToMethod(
            InstanceOfExpr check,
            MethodDeclaration method) {

        Node current = check.getParentNode().orElse(null);

        while (current != null) {
            if (current instanceof MethodDeclaration enclosing) {
                return enclosing == method;
            }

            current = current.getParentNode().orElse(null);
        }

        return false;
    }

    private Map<String, ClassOrInterfaceDeclaration>
            indexConcreteClasses(RepositoryParseResult repository) {

        Map<String, ClassOrInterfaceDeclaration> index =
                new LinkedHashMap<>();

        var files = repository.parsedFiles()
                .entrySet()
                .stream()
                .sorted(Comparator.comparing(
                        entry -> entry.getKey().toString()))
                .toList();

        for (Map.Entry<Path, CompilationUnit> entry : files) {

            for (ClassOrInterfaceDeclaration type :
                    entry.getValue().findAll(
                            ClassOrInterfaceDeclaration.class)) {

                if (type.isInterface() || type.isAbstract()) {
                    continue;
                }

                type.getFullyQualifiedName()
                        .ifPresent(name ->
                                index.putIfAbsent(name, type));
            }
        }

        return index;
    }

    /**
     * Resolve against repository-known concrete classes.
     * A fallback is allowed only for the same package or
     * an explicit import.
     */
    private String resolveRepositoryClass(
            ClassOrInterfaceType type,
            CompilationUnit unit,
            Map<String, ClassOrInterfaceDeclaration> classes) {

        try {
            String qualified = type.resolve()
                    .asReferenceType()
                    .getQualifiedName();

            if (classes.containsKey(qualified)) {
                return qualified;
            }

        } catch (RuntimeException exception) {
            // Attempt conservative source-based lookup.
        }

        String name = type.getNameWithScope();

        if (name.contains(".")) {
            return classes.containsKey(name) ? name : null;
        }

        String packageName = unit.getPackageDeclaration()
                .map(declaration ->
                        declaration.getNameAsString())
                .orElse("");

        String samePackage = packageName.isEmpty()
                ? name
                : packageName + "." + name;

        if (classes.containsKey(samePackage)) {
            return samePackage;
        }

        List<String> imports = unit.getImports()
                .stream()
                .filter(declaration ->
                        !declaration.isStatic()
                                && !declaration.isAsterisk())
                .map(declaration ->
                        declaration.getNameAsString())
                .filter(qualified ->
                        qualified.endsWith("." + name)
                                && classes.containsKey(qualified))
                .distinct()
                .toList();

        return imports.size() == 1 ? imports.get(0) : null;
    }
}
