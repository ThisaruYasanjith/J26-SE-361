package org.j26.architecture;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.ast.type.ClassOrInterfaceType;
import org.j26.architecture.model.ComponentInfo;
import org.j26.architecture.model.EntityType;
import org.j26.architecture.model.SourceLocation;
import org.j26.architecture.model.SpringType;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class ArchitectureEntityExtractor {
    public List<ComponentInfo> extract(CompilationUnit unit, Path projectRoot, Path sourceFile) {
        Path root = projectRoot.toAbsolutePath().normalize();
        Path file = sourceFile.toAbsolutePath().normalize();
        if (!file.startsWith(root)) {
            throw new IllegalArgumentException("Source file must be inside the analyzed project: " + file);
        }

        String relativePath = root.relativize(file).toString().replace('\\', '/');
        String packageName = unit.getPackageDeclaration()
                .map(declaration -> declaration.getNameAsString()).orElse("");
        List<ComponentInfo> components = new ArrayList<>();

        // Only visit top-level declarations. Searching the whole AST would also include nested classes.
        for (TypeDeclaration<?> type : unit.getTypes()) {
            if (!type.isClassOrInterfaceDeclaration()) {
                continue;
            }
            ClassOrInterfaceDeclaration declaration = type.asClassOrInterfaceDeclaration();
            // Programmatically created AST nodes may have no range. Never invent line numbers.
            if (declaration.getRange().isEmpty()) {
                continue;
            }
            var range = declaration.getRange().orElseThrow();
            if (range.begin.line < 1 || range.end.line < range.begin.line) {
                continue;
            }

            // Repeated annotations share a name, while the context contract expects unique names.
            List<String> annotations = declaration.getAnnotations().stream()
                    .map(annotation -> annotation.getNameAsString()).distinct().toList();
            SpringType springType = SpringType.NONE;
            for (String annotation : annotations) {
                SpringType candidate = springTypeFor(annotation);
                // A specific stereotype takes precedence over a generic @Component.
                if (candidate != SpringType.NONE
                        && (springType == SpringType.NONE || springType == SpringType.COMPONENT)) {
                    springType = candidate;
                }
            }

            boolean isInterface = declaration.isInterface();
            // Keep declared names and qualifiers without resolving imports or generic arguments.
            List<String> extendedTypes = declaration.getExtendedTypes().stream()
                    .map(ClassOrInterfaceType::getNameWithScope).toList();
            List<String> implementedInterfaces = declaration.getImplementedTypes().stream()
                    .map(ClassOrInterfaceType::getNameWithScope).toList();
            String name = packageName.isEmpty() ? declaration.getNameAsString()
                    : packageName + "." + declaration.getNameAsString();

            components.add(new ComponentInfo(
                    name,
                    isInterface ? EntityType.INTERFACE : EntityType.CLASS,
                    springType,
                    packageName,
                    relativePath,
                    annotations,
                    new SourceLocation(range.begin.line, range.end.line),
                    !isInterface && !extendedTypes.isEmpty() ? extendedTypes.get(0) : null,
                    implementedInterfaces,
                    isInterface ? extendedTypes : List.of()));
        }

        return List.copyOf(components);
    }

    private SpringType springTypeFor(String annotation) {
        // Simple names are recognized as written. Import and symbol resolution are separate work.
        return switch (annotation) {
            case "RestController", "Controller",
                    "org.springframework.web.bind.annotation.RestController",
                    "org.springframework.stereotype.Controller" -> SpringType.CONTROLLER;
            case "Service", "org.springframework.stereotype.Service" -> SpringType.SERVICE;
            case "Repository", "org.springframework.stereotype.Repository" -> SpringType.REPOSITORY;
            case "Component", "org.springframework.stereotype.Component" -> SpringType.COMPONENT;
            case "Configuration", "org.springframework.context.annotation.Configuration" -> SpringType.CONFIGURATION;
            default -> SpringType.NONE;
        };
    }
}
