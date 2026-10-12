package lk.sliit.codecleanliness;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.type.ClassOrInterfaceType;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;

public class RepositoryRelationshipBuilder {

    public List<JavaRelationshipInfo> build(
            RepositoryParseResult result) {

        List<JavaRelationshipInfo> relationships =
                new ArrayList<>();

        for (Map.Entry<Path, CompilationUnit> entry :
                result.parsedFiles().entrySet()) {

            Path sourceFile = entry.getKey();
            CompilationUnit unit = entry.getValue();

            for (ClassOrInterfaceDeclaration declaration :
                    unit.findAll(ClassOrInterfaceDeclaration.class)) {

                String sourceType = declaration
                        .getFullyQualifiedName()
                        .orElse(declaration.getNameAsString());

                for (ClassOrInterfaceType parent :
                        declaration.getExtendedTypes()) {

                    relationships.add(resolveTypeRelationship(
                            sourceFile,
                            sourceType,
                            parent,
                            JavaRelationshipInfo.RelationshipKind.EXTENDS
                    ));
                }

                for (ClassOrInterfaceType implemented :
                        declaration.getImplementedTypes()) {

                    relationships.add(resolveTypeRelationship(
                            sourceFile,
                            sourceType,
                            implemented,
                            JavaRelationshipInfo.RelationshipKind.IMPLEMENTS
                    ));
                }

                for (MethodDeclaration method :
                        declaration.getMethods()) {

                    for (MethodCallExpr call :
                            method.findAll(MethodCallExpr.class)) {

                        relationships.add(resolveMethodCall(
                                sourceFile,
                                sourceType,
                                method.getNameAsString(),
                                call
                        ));
                    }
                }
            }
        }

        relationships.sort(
                Comparator.comparing(
                        (JavaRelationshipInfo r) ->
                                r.sourceFile().toString()
                ).thenComparingInt(JavaRelationshipInfo::line)
                 .thenComparing(r -> r.kind().name())
                 .thenComparing(JavaRelationshipInfo::target)
        );

        return List.copyOf(relationships);
    }

    private JavaRelationshipInfo resolveTypeRelationship(
            Path sourceFile,
            String sourceType,
            ClassOrInterfaceType type,
            JavaRelationshipInfo.RelationshipKind kind) {

        String target;
        JavaRelationshipInfo.ResolutionStatus status;

        try {
            target = type.resolve()
                    .asReferenceType()
                    .getQualifiedName();

            status =
                    JavaRelationshipInfo.ResolutionStatus.RESOLVED;

        } catch (RuntimeException ex) {
            target = type.asString();

            status =
                    JavaRelationshipInfo.ResolutionStatus.UNRESOLVED;
        }

        return new JavaRelationshipInfo(
                sourceFile,
                sourceType,
                null,
                kind,
                target,
                status,
                lineOf(type)
        );
    }

    private JavaRelationshipInfo resolveMethodCall(
            Path sourceFile,
            String sourceType,
            String sourceMethod,
            MethodCallExpr call) {

        String target;
        JavaRelationshipInfo.ResolutionStatus status;

        try {
            target = call.resolve().getQualifiedSignature();

            status =
                    JavaRelationshipInfo.ResolutionStatus.RESOLVED;

        } catch (RuntimeException ex) {
            target = call.toString();

            status =
                    JavaRelationshipInfo.ResolutionStatus.UNRESOLVED;
        }

        return new JavaRelationshipInfo(
                sourceFile,
                sourceType,
                sourceMethod,
                JavaRelationshipInfo.RelationshipKind.METHOD_CALL,
                target,
                status,
                lineOf(call)
        );
    }

    private int lineOf(com.github.javaparser.ast.Node node) {
        return node.getBegin()
                .map(position -> position.line)
                .orElse(-1);
    }
}