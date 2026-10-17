
package lk.sliit.codecleanliness.detection;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.ImportDeclaration;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.stmt.ThrowStmt;
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
 * Preliminary evidence-based ISP risk detection.
 *
 * Reports a candidate only when:
 * 1. A class explicitly implements an interface.
 * 2. That interface resolves to a declaration in the
 *    analyzed repository.
 * 3. A class method matches a declared interface method.
 * 4. The matching implementation explicitly throws
 *    UnsupportedOperationException.
 *
 * Unresolved and ambiguous contracts are skipped.
 *
 * This does not prove an ISP violation or imply that
 * splitting the interface is necessarily appropriate.
 */
public class IspRiskDetector {

    public List<MaintainabilityFinding> detect(
            RepositoryParseResult repository) {

        Objects.requireNonNull(
                repository, "Repository parse result is required"
        );

        Map<String, ClassOrInterfaceDeclaration> interfaces =
                indexInterfaces(repository);

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

            for (ClassOrInterfaceDeclaration type :
                    entry.getValue().findAll(
                            ClassOrInterfaceDeclaration.class)) {

                if (type.isInterface()
                        || type.getImplementedTypes().isEmpty()) {
                    continue;
                }

                String className = type.getFullyQualifiedName()
                        .orElse(type.getNameAsString());

                for (MethodDeclaration method : type.getMethods()) {

                    if (method.getBody().isEmpty()
                            || method.getRange().isEmpty()
                            || method.isStatic()) {
                        continue;
                    }

                    List<ThrowStmt> unsupported =
                            unsupportedThrows(method);

                    if (unsupported.isEmpty()) {
                        continue;
                    }

                    List<String> matchedInterfaces =
                            new ArrayList<>();

                    for (ClassOrInterfaceType implemented :
                            type.getImplementedTypes()) {

                        ClassOrInterfaceDeclaration contract =
                                resolveRepositoryInterface(
                                        implemented,
                                        type,
                                        interfaces
                                );

                        if (contract == null) {
                            continue;
                        }

                        String interfaceName = contract
                                .getFullyQualifiedName()
                                .orElse(contract.getNameAsString());

                        boolean matches = contract.getMethods()
                                .stream()
                                .anyMatch(required ->
                                        sameSignature(method, required));

                        if (matches) {
                            matchedInterfaces.add(interfaceName);
                        }
                    }

                    if (matchedInterfaces.isEmpty()) {
                        continue;
                    }

                    matchedInterfaces.sort(String::compareTo);

                    int start = method.getRange()
                            .orElseThrow().begin.line;

                    int end = method.getRange()
                            .orElseThrow().end.line;

                    String symbol = className + "."
                            + method.getSignature().asString();

                    findings.add(new MaintainabilityFinding(
                            file + ":" + start + ":" + symbol
                                    + ":ISP_RISK",
                            MaintainabilityConcern.ISP_RISK,
                            FindingScope.METHOD,
                            file,
                            symbol,
                            start,
                            end,
                            "INTERFACE_CONTRACT_OPERATION_UNSUPPORTED",
                            "An implementation of a declared "
                                    + "interface operation explicitly "
                                    + "throws UnsupportedOperationException. "
                                    + "Review whether the interface contract "
                                    + "requires an unsupported responsibility.",
                            Map.of(
                                    "implementingClass", className,
                                    "matchedInterfaces",
                                    String.join(", ", matchedInterfaces),
                                    "methodSignature",
                                    method.getSignature().asString(),
                                    "unsupportedThrowCount",
                                    String.valueOf(unsupported.size()),
                                    "measurement",
                                    "resolved_direct_interface_contract_pattern"
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

    private Map<String, ClassOrInterfaceDeclaration> indexInterfaces(
            RepositoryParseResult repository) {

        Map<String, ClassOrInterfaceDeclaration> index =
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

                if (!declaration.isInterface()) {
                    continue;
                }

                declaration.getFullyQualifiedName()
                        .ifPresent(name ->
                                index.putIfAbsent(name, declaration));
            }
        }

        return index;
    }

    
/**
 * Finds a directly implemented interface in the
 * analyzed repository.
 *
 * Uses symbol resolution first. When resolution is
 * unavailable, accepts only an unambiguous repository
 * declaration identified by package or explicit import.
 *
 * Does not guess using an arbitrary simple-name match.
 */
private ClassOrInterfaceDeclaration resolveRepositoryInterface(
        ClassOrInterfaceType implemented,
        ClassOrInterfaceDeclaration implementingType,
        Map<String, ClassOrInterfaceDeclaration> interfaces) {

    String resolvedName = resolveInterfaceName(implemented);

    if (resolvedName != null) {
        ClassOrInterfaceDeclaration resolved =
                interfaces.get(resolvedName);

        if (resolved != null) {
            return resolved;
        }
    }

    var unit = implementingType.findCompilationUnit();

    if (unit.isEmpty()) {
        return null;
    }

    String declaredName = implemented.getNameWithScope();

    // A fully qualified type reference must match exactly.
    if (declaredName.contains(".")) {
        return interfaces.get(declaredName);
    }

    String packageName = unit.get()
            .getPackageDeclaration()
            .map(declaration -> declaration.getNameAsString())
            .orElse("");

    String samePackageName = packageName.isEmpty()
            ? declaredName
            : packageName + "." + declaredName;

    ClassOrInterfaceDeclaration samePackage =
            interfaces.get(samePackageName);

    if (samePackage != null) {
        return samePackage;
    }

        // Support explicitly imported interfaces in
        // another package. Wildcard imports are not
        // inferred because they may be ambiguous.
        List<String> importedNames = unit.get()
                .getImports()
                .stream()
                .filter(importDeclaration ->
                        !importDeclaration.isStatic()
                        && !importDeclaration.isAsterisk())
                .map(ImportDeclaration::getNameAsString)
                .filter(name ->
                        name.endsWith("." + declaredName))
                .distinct()
                .toList();

        if (importedNames.size() != 1) {
            return null;
        }

        return interfaces.get(importedNames.get(0));
    }

    private String resolveInterfaceName(
            ClassOrInterfaceType type) {

        try {
            var resolved = type.resolve();

            if (!resolved.isReferenceType()) {
                return null;
            }

            return resolved.asReferenceType()
                    .getQualifiedName();

        } catch (RuntimeException exception) {
            // Do not infer a contract using an
            // ambiguous or unresolved simple name.
            return null;
        }
    }

    private boolean sameSignature(
            MethodDeclaration implementation,
            MethodDeclaration contract) {

        if (!implementation.getNameAsString()
                .equals(contract.getNameAsString())) {
            return false;
        }

        if (implementation.getParameters().size()
                != contract.getParameters().size()) {
            return false;
        }

        // Conservative source-level parameter matching.
        // Generic substitution and inherited interface
        // signatures are not covered by this stage.
        for (int i = 0;
             i < implementation.getParameters().size();
             i++) {

            var actual = implementation.getParameter(i);
            var required = contract.getParameter(i);

            if (!actual.getType().asString()
                    .equals(required.getType().asString())) {
                return false;
            }

            if (actual.isVarArgs() != required.isVarArgs()) {
                return false;
            }
        }

        return true;
    }

    private List<ThrowStmt> unsupportedThrows(
            MethodDeclaration method) {

        return method.getBody()
                .orElseThrow()
                .findAll(ThrowStmt.class)
                .stream()
                .filter(statement ->
                        statement.getExpression()
                                .isObjectCreationExpr())
                .filter(statement -> {
                    String name = statement.getExpression()
                            .asObjectCreationExpr()
                            .getType()
                            .asString();

                    return name.equals(
                            "UnsupportedOperationException")
                            || name.equals(
                            "java.lang.UnsupportedOperationException");
                })
                .filter(statement -> {
                    Node parent = statement.getParentNode()
                            .orElse(null);

                    while (parent != null) {
                        if (parent instanceof MethodDeclaration owner) {
                            return owner == method;
                        }
                        parent = parent.getParentNode()
                                .orElse(null);
                    }

                    return false;
                })
                .toList();
    }
}
