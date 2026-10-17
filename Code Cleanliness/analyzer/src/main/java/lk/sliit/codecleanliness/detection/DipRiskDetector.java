
package lk.sliit.codecleanliness.detection;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.FieldDeclaration;
import com.github.javaparser.ast.body.VariableDeclarator;
import com.github.javaparser.ast.expr.ObjectCreationExpr;
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

/**
 * Preliminary Dependency Inversion Principle risk detector.
 *
 * Reports a review candidate when:
 * - a non-static field is declared using a concrete class;
 * - the same field directly constructs that concrete class;
 * - the class declaration is found in the analyzed repository.
 *
 * Does not equate all object creation with DIP violations.
 */
public class DipRiskDetector {

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

                for (FieldDeclaration field : owner.getFields()) {

                    if (field.isStatic()) {
                        continue;
                    }

                    for (VariableDeclarator variable :
                            field.getVariables()) {

                        if (!variable.getType()
                                .isClassOrInterfaceType()) {
                            continue;
                        }

                        if (variable.getInitializer().isEmpty()
                                || !variable.getInitializer()
                                        .orElseThrow()
                                        .isObjectCreationExpr()) {
                            continue;
                        }

                        ClassOrInterfaceType declaredType =
                                variable.getType()
                                        .asClassOrInterfaceType();

                        ObjectCreationExpr initializer =
                                variable.getInitializer()
                                        .orElseThrow()
                                        .asObjectCreationExpr();

                        String dependencyName =
                                resolveRepositoryClass(
                                        declaredType,
                                        unit,
                                        classes
                                );

                        String constructedName =
                                resolveRepositoryClass(
                                        initializer.getType(),
                                        unit,
                                        classes
                                );

                        if (dependencyName == null
                                || !dependencyName.equals(
                                        constructedName)
                                || dependencyName.equals(ownerName)) {
                            continue;
                        }

                        int line = variable.getBegin()
                                .map(position -> position.line)
                                .orElse(-1);

                        if (line < 1) {
                            continue;
                        }

                        String symbol = ownerName + "."
                                + variable.getNameAsString();

                        findings.add(new MaintainabilityFinding(
                                file + ":" + line + ":" + symbol
                                        + ":DIP_RISK",
                                MaintainabilityConcern.DIP_RISK,
                                FindingScope.FIELD,
                                file,
                                symbol,
                                line,
                                line,
                                "CONCRETE_FIELD_DIRECT_CONSTRUCTION",
                                "An instance field is typed as a "
                                        + "concrete repository class and "
                                        + "directly constructs that class. "
                                        + "Review whether this dependency "
                                        + "should be supplied through an "
                                        + "abstraction or injection.",
                                Map.of(
                                        "owningClass", ownerName,
                                        "fieldName",
                                        variable.getNameAsString(),
                                        "declaredType", dependencyName,
                                        "constructedType", constructedName,
                                        "initializer",
                                        initializer.toString(),
                                        "measurement",
                                        "direct_concrete_field_construction"
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

    private Map<String, ClassOrInterfaceDeclaration>
            indexConcreteClasses(RepositoryParseResult repository) {

        Map<String, ClassOrInterfaceDeclaration> classes =
                new LinkedHashMap<>();

        var files = repository.parsedFiles()
                .entrySet()
                .stream()
                .sorted(Comparator.comparing(
                        entry -> entry.getKey().toString()))
                .toList();

        for (Map.Entry<Path, CompilationUnit> entry : files) {

            for (ClassOrInterfaceDeclaration declaration :
                    entry.getValue().findAll(
                            ClassOrInterfaceDeclaration.class)) {

                if (declaration.isInterface()
                        || declaration.isAbstract()) {
                    continue;
                }

                declaration.getFullyQualifiedName()
                        .ifPresent(name ->
                                classes.putIfAbsent(
                                        name,
                                        declaration
                                ));
            }
        }

        return classes;
    }

    /**
     * Resolve only classes indexed from the repository.
     * Fallbacks are constrained to the same package
     * or an explicit single-type import.
     */
    private String resolveRepositoryClass(
            ClassOrInterfaceType type,
            CompilationUnit unit,
            Map<String, ClassOrInterfaceDeclaration> classes) {

        try {
            var resolved = type.resolve();

            if (resolved.isReferenceType()) {
                String qualified = resolved.asReferenceType()
                        .getQualifiedName();

                if (classes.containsKey(qualified)) {
                    return qualified;
                }
            }

        } catch (RuntimeException exception) {
            // Continue with conservative source lookup.
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
