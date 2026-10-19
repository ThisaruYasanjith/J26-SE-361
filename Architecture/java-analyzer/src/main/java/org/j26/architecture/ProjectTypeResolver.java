package org.j26.architecture;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.CallableDeclaration;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.ast.nodeTypes.NodeWithTypeParameters;
import com.github.javaparser.ast.type.Type;
import org.j26.architecture.model.ComponentInfo;

import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;

final class ProjectTypeResolver {
    private final Set<String> projectTypes;

    ProjectTypeResolver(List<ComponentInfo> components) {
        projectTypes = components.stream().map(ComponentInfo::name)
                .filter(name -> !isFrameworkType(name)).collect(Collectors.toUnmodifiableSet());
    }

    Optional<String> projectType(String qualifiedName) {
        return projectTypes.contains(qualifiedName) ? Optional.of(qualifiedName) : Optional.empty();
    }

    Optional<String> resolve(Type type, CompilationUnit unit, Node context) {
        if (!type.isClassOrInterfaceType()) {
            return Optional.empty();
        }
        return resolve(type.asClassOrInterfaceType().getNameWithScope(), unit, context);
    }

    Optional<String> resolve(String name, CompilationUnit unit, Node context) {
        if (isFrameworkType(name) || isShadowedTypeName(name, context)) {
            return Optional.empty();
        }
        if (name.contains(".")) {
            return projectType(name);
        }

        String packageName = unit.getPackageDeclaration().map(declaration -> declaration.getNameAsString()).orElse("");
        String samePackageName = packageName.isEmpty() ? name : packageName + "." + name;
        // A type declared in this file also shadows imports, including unsupported records and enums.
        if (unit.getTypes().stream().anyMatch(type -> type.getNameAsString().equals(name))) {
            return projectType(samePackageName);
        }

        List<String> imports = unit.getImports().stream()
                .filter(declaration -> !declaration.isStatic() && !declaration.isAsterisk())
                .filter(declaration -> declaration.getName().getIdentifier().equals(name))
                .map(declaration -> declaration.getNameAsString()).distinct().toList();
        if (!imports.isEmpty()) {
            // An explicit external import must not fall back to a same-named project class.
            return imports.size() == 1 ? projectType(imports.get(0)) : Optional.empty();
        }

        // No global simple-name guessing or wildcard expansion: both can bind the wrong class.
        return projectType(samePackageName);
    }

    private boolean isShadowedTypeName(String name, Node context) {
        String firstPart = name.split("\\.", 2)[0];
        for (Node current = context; current != null; current = current.getParentNode().orElse(null)) {
            if (current instanceof NodeWithTypeParameters<?> declaration
                    && declaration.getTypeParameters().stream().anyMatch(type -> type.getNameAsString().equals(firstPart))) {
                return true;
            }
            if (current instanceof ClassOrInterfaceDeclaration owner
                    && owner.getMembers().stream().filter(member -> member instanceof TypeDeclaration<?>)
                    .map(member -> (TypeDeclaration<?>) member)
                    .anyMatch(type -> type.getNameAsString().equals(firstPart))) {
                return true;
            }
            if (current instanceof CallableDeclaration<?> callable
                    && callable.findAll(ClassOrInterfaceDeclaration.class).stream()
                    .anyMatch(type -> type.getNameAsString().equals(firstPart))) {
                return true;
            }
        }
        return false;
    }

    private static boolean isFrameworkType(String name) {
        return name.startsWith("java.") || name.startsWith("javax.")
                || name.startsWith("jakarta.") || name.startsWith("org.springframework.");
    }
}
