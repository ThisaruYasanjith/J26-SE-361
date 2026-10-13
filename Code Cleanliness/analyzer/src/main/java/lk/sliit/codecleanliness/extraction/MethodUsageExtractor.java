package lk.sliit.codecleanliness.extraction;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.FieldAccessExpr;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.NameExpr;

import lk.sliit.codecleanliness.model.MethodUsageInfo;
import lk.sliit.codecleanliness.model.RepositoryParseResult;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class MethodUsageExtractor {

    public List<MethodUsageInfo> extract(
            RepositoryParseResult result) {

        List<MethodUsageInfo> usages = new ArrayList<>();

        for (Map.Entry<Path, CompilationUnit> entry :
                result.parsedFiles().entrySet()) {

            for (ClassOrInterfaceDeclaration type :
                    entry.getValue().findAll(
                            ClassOrInterfaceDeclaration.class)) {

                String owner = type.getFullyQualifiedName()
                        .orElse(type.getNameAsString());

                for (MethodDeclaration method : type.getMethods()) {

                    Set<String> fields = new LinkedHashSet<>();
                    Set<String> calls = new LinkedHashSet<>();
                    List<String> unresolved = new ArrayList<>();

                    if (method.getBody().isPresent()) {

                        var body = method.getBody().orElseThrow();

                        for (NameExpr name :
                                body.findAll(NameExpr.class)) {

                            try {
                                var resolved = name.resolve();

                                if (resolved.isField()) {
                                    var field = resolved.asField();

                                    if (field.declaringType()
                                            .getQualifiedName()
                                            .equals(owner)) {
                                        fields.add(field.getName());
                                    }
                                }

                            } catch (RuntimeException ex) {
                                unresolved.add(
                                        "FIELD_REFERENCE: " + name
                                );
                            }
                        }

                        for (FieldAccessExpr access :
                                body.findAll(FieldAccessExpr.class)) {

                            try {
                                var resolved = access.resolve();

                                if (resolved.isField()) {
                                    var field = resolved.asField();

                                    if (field.declaringType()
                                            .getQualifiedName()
                                            .equals(owner)) {
                                        fields.add(field.getName());
                                    }
                                }

                            } catch (RuntimeException ex) {
                                unresolved.add(
                                        "FIELD_ACCESS: " + access
                                );
                            }
                        }

                        for (MethodCallExpr call :
                                body.findAll(MethodCallExpr.class)) {

                            try {
                                var resolved = call.resolve();

                                if (resolved.declaringType()
                                        .getQualifiedName()
                                        .equals(owner)) {
                                    calls.add(
                                            resolved.getQualifiedSignature()
                                    );
                                }

                            } catch (RuntimeException ex) {
                                unresolved.add(
                                        "METHOD_CALL: " + call
                                );
                            }
                        }
                    }

                    usages.add(new MethodUsageInfo(
                            entry.getKey(),
                            owner,
                            method.getSignature().asString(),
                            method.getBegin()
                                    .map(p -> p.line)
                                    .orElse(-1),
                            List.copyOf(fields),
                            List.copyOf(calls),
                            List.copyOf(unresolved)
                    ));
                }
            }
        }

        return List.copyOf(usages);
    }
}