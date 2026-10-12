package lk.sliit.codecleanliness.metrics;

import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.FieldDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;

public class ClassMetricsCalculator {

    private final MethodMetricsCalculator methodCalculator;

    public ClassMetricsCalculator() {
        this.methodCalculator = new MethodMetricsCalculator();
    }

    public ClassMetrics calculate(ClassOrInterfaceDeclaration declaration) {

        int methodCount = declaration.getMethods().size();

        int fieldCount = 0;

        for (FieldDeclaration field : declaration.getFields()) {
            fieldCount += field.getVariables().size();
        }

        int methodNcssTotal = 0;
        int weightedMethodCount = 0;

        for (MethodDeclaration method : declaration.getMethods()) {

            MethodMetrics metrics = methodCalculator.calculate(method);

            methodNcssTotal += metrics.ncss();

            weightedMethodCount += metrics.cyclomaticComplexity();
        }

        // Initial class-NCSS convention:
        // declared field variables + NCSS of directly declared methods.
        int classNcss = fieldCount + methodNcssTotal;

        return new ClassMetrics(
                declaration.getFullyQualifiedName()
                        .orElse(declaration.getNameAsString()),
                declaration.getBegin()
                        .map(position -> position.line)
                        .orElse(-1),
                classNcss,
                methodCount,
                fieldCount,
                weightedMethodCount
        );
    }
}