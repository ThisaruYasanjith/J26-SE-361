package lk.sliit.codecleanliness.metrics;

import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.expr.FieldAccessExpr;
import com.github.javaparser.ast.expr.NameExpr;
import com.github.javaparser.resolution.declarations.ResolvedValueDeclaration;

import java.util.Set;
import java.util.TreeSet;

public class AtfdMetricsCalculator {

    public AtfdMetrics calculate(
            ClassOrInterfaceDeclaration declaration) {

        String owner = declaration.getFullyQualifiedName()
                .orElse(declaration.getNameAsString());

        Set<String> foreignFields = new TreeSet<>();
        int unresolvedCount = 0;

        for (var method : declaration.getMethods()) {
            if (method.getBody().isEmpty()) {
                continue;
            }

            var body = method.getBody().orElseThrow();

            for (NameExpr name : body.findAll(NameExpr.class)) {
                try {
                    collect(name.resolve(), owner, foreignFields);
                } catch (RuntimeException ex) {
                    unresolvedCount++;
                }
            }

            for (FieldAccessExpr access :
                    body.findAll(FieldAccessExpr.class)) {
                try {
                    collect(access.resolve(), owner, foreignFields);
                } catch (RuntimeException ex) {
                    unresolvedCount++;
                }
            }
        }

        return new AtfdMetrics(
                owner,
                foreignFields.size(),
                foreignFields.stream().toList(),
                unresolvedCount
        );
    }

    private void collect(
            ResolvedValueDeclaration resolved,
            String owner,
            Set<String> foreignFields) {

        if (!resolved.isField()) {
            return;
        }

        var field = resolved.asField();

        String declaringType =
                field.declaringType().getQualifiedName();

        if (!declaringType.equals(owner)) {
            foreignFields.add(
                    declaringType + "." + field.getName()
            );
        }
    }
}