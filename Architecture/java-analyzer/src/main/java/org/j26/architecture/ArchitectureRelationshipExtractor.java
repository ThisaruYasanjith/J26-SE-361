package org.j26.architecture;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.ObjectCreationExpr;
import com.github.javaparser.ast.type.Type;
import org.j26.architecture.model.ComponentInfo;
import org.j26.architecture.model.RelationshipInfo;
import org.j26.architecture.model.RelationshipType;
import org.j26.architecture.model.SourceLocation;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import java.util.stream.Collectors;

public final class ArchitectureRelationshipExtractor {
    public List<RelationshipInfo> extract(List<CompilationUnit> units, List<ComponentInfo> components) {
        ProjectTypeResolver types = new ProjectTypeResolver(components);
        MethodCallTargetResolver calls = new MethodCallTargetResolver(types);
        Map<String, ComponentInfo> byName = components.stream().collect(Collectors.toMap(
                ComponentInfo::name, component -> component, (first, second) -> first, LinkedHashMap::new));
        Map<RelationshipKey, RelationshipInfo> relationships = new LinkedHashMap<>();

        for (CompilationUnit unit : units) {
            String packageName = unit.getPackageDeclaration().map(declaration -> declaration.getNameAsString()).orElse("");
            for (TypeDeclaration<?> declaration : unit.getTypes()) {
                if (!declaration.isClassOrInterfaceDeclaration()) {
                    continue;
                }
                ClassOrInterfaceDeclaration owner = declaration.asClassOrInterfaceDeclaration();
                String source = packageName.isEmpty() ? owner.getNameAsString() : packageName + "." + owner.getNameAsString();
                ComponentInfo component = byName.get(source);
                if (component == null) {
                    continue;
                }

                Consumer<RelationshipInfo> add = relationship -> addRelationship(relationships, relationship);
                unit.getImports().stream().filter(imported -> !imported.isStatic() && !imported.isAsterisk())
                        .forEach(imported -> types.projectType(imported.getNameAsString()).ifPresent(target ->
                                add.accept(relationship(source, target, RelationshipType.IMPORTS, imported))));

                List<String> parents = owner.isInterface() ? component.extendedInterfaces()
                        : component.extendsClass() == null ? List.of() : List.of(component.extendsClass());
                addInheritance(parents, new ArrayList<>(owner.getExtendedTypes()), RelationshipType.EXTENDS,
                        source, unit, owner, types, add);
                addInheritance(component.implementedInterfaces(), new ArrayList<>(owner.getImplementedTypes()),
                        RelationshipType.IMPLEMENTS, source, unit, owner, types, add);

                owner.getFields().forEach(field -> field.getVariables().forEach(variable ->
                        addDependencies(variable.getType(), source, unit, types, add)));
                owner.getConstructors().forEach(constructor -> constructor.getParameters().forEach(parameter ->
                        addDependencies(parameter.getType(), source, unit, types, add)));

                owner.findAll(ObjectCreationExpr.class).stream().filter(node -> belongsTo(node, owner))
                        .forEach(creation -> types.resolve(creation.getType(), unit, creation).ifPresent(target ->
                                add.accept(relationship(source, target, RelationshipType.DEPENDS_ON, creation.getType()))));
                owner.findAll(MethodCallExpr.class).stream().filter(node -> belongsTo(node, owner))
                        .forEach(call -> calls.resolve(call, unit, owner).ifPresent(target ->
                                add.accept(relationship(source, target, RelationshipType.CALLS, call))));
            }
        }

        return relationships.values().stream().sorted(Comparator.comparing(RelationshipInfo::source)
                .thenComparing(RelationshipInfo::target).thenComparing(edge -> edge.relationship().name())).toList();
    }

    private void addDependencies(Type type, String source, CompilationUnit unit, ProjectTypeResolver types,
                                 Consumer<RelationshipInfo> add) {
        if (type.isArrayType()) {
            addDependencies(type.asArrayType().getComponentType(), source, unit, types, add);
        } else if (type.isClassOrInterfaceType()) {
            types.resolve(type, unit, type).ifPresent(target ->
                    add.accept(relationship(source, target, RelationshipType.DEPENDS_ON, type)));
            // List<Repository> depends on the project Repository, not on the external List container.
            type.asClassOrInterfaceType().getTypeArguments().ifPresent(arguments -> arguments.forEach(argument ->
                    addDependencies(argument, source, unit, types, add)));
        } else if (type.isWildcardType()) {
            type.asWildcardType().getExtendedType().ifPresent(bound -> addDependencies(bound, source, unit, types, add));
            type.asWildcardType().getSuperType().ifPresent(bound -> addDependencies(bound, source, unit, types, add));
        }
    }

    private void addInheritance(List<String> names, List<? extends Node> references, RelationshipType relationship,
                                String source, CompilationUnit unit, ClassOrInterfaceDeclaration owner,
                                ProjectTypeResolver types, Consumer<RelationshipInfo> add) {
        for (int i = 0; i < names.size(); i++) {
            Node reference = i < references.size() ? references.get(i) : null;
            types.resolve(names.get(i), unit, reference == null ? owner : reference).ifPresent(target ->
                    add.accept(relationship(source, target, relationship, reference)));
        }
    }

    private boolean belongsTo(Node node, ClassOrInterfaceDeclaration owner) {
        Node branch = node;
        for (Node parent = node.getParentNode().orElse(null); parent != null;
             branch = parent, parent = parent.getParentNode().orElse(null)) {
            if (parent == owner) {
                return true;
            }
            // Nested and anonymous class bodies belong to entities that are not modeled yet.
            if (parent instanceof TypeDeclaration<?>) {
                return false;
            }
            if (parent instanceof ObjectCreationExpr creation && creation.getAnonymousClassBody().isPresent()) {
                for (var member : creation.getAnonymousClassBody().orElseThrow()) {
                    if (member == branch) {
                        return false;
                    }
                }
            }
        }
        return false;
    }

    private RelationshipInfo relationship(String source, String target, RelationshipType type, Node reference) {
        SourceLocation location = reference == null ? null : reference.getRange()
                .filter(range -> range.begin.line > 0 && range.end.line >= range.begin.line)
                .map(range -> new SourceLocation(range.begin.line, range.end.line)).orElse(null);
        return new RelationshipInfo(source, target, type, location);
    }

    private void addRelationship(Map<RelationshipKey, RelationshipInfo> relationships, RelationshipInfo candidate) {
        RelationshipKey key = new RelationshipKey(candidate.source(), candidate.target(), candidate.relationship());
        relationships.merge(key, candidate, (existing, incoming) -> {
            SourceLocation oldLocation = existing.sourceLocation();
            SourceLocation newLocation = incoming.sourceLocation();
            // Different extraction passes can see the same edge. Keep its earliest known source span.
            if (newLocation != null && (oldLocation == null || newLocation.startLine() < oldLocation.startLine()
                    || newLocation.startLine() == oldLocation.startLine() && newLocation.endLine() < oldLocation.endLine())) {
                return incoming;
            }
            return existing;
        });
    }

    private record RelationshipKey(String source, String target, RelationshipType relationship) {
    }
}
