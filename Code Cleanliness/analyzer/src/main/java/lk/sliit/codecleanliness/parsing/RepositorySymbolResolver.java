package lk.sliit.codecleanliness.parsing;

import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.type.ClassOrInterfaceType;
import com.github.javaparser.resolution.declarations.ResolvedMethodDeclaration;
import com.github.javaparser.symbolsolver.JavaSymbolSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.ReflectionTypeSolver;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class RepositorySymbolResolver {

    private final CombinedTypeSolver typeSolver;

    public RepositorySymbolResolver(Path repositoryRoot) {

        Objects.requireNonNull(repositoryRoot,
                "Repository root cannot be null.");

        if (!Files.isDirectory(repositoryRoot)) {
            throw new IllegalArgumentException(
                    "Repository root must be an existing directory."
            );
        }

        typeSolver = new CombinedTypeSolver();
        typeSolver.add(new ReflectionTypeSolver());

        registerSourceRoot(repositoryRoot.resolve("src/main/java"));
        registerSourceRoot(repositoryRoot.resolve("src/test/java"));
    }

    private void registerSourceRoot(Path sourceRoot) {
        if (Files.isDirectory(sourceRoot)) {
            typeSolver.add(new JavaParserTypeSolver(sourceRoot));
        }
    }

    public ParserConfiguration createParserConfiguration() {
        return new ParserConfiguration()
                .setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_17)
                .setSymbolResolver(new JavaSymbolSolver(typeSolver));
    }

    public List<String> resolveMethodCalls(CompilationUnit unit) {

        List<String> resolvedCalls = new ArrayList<>();

        for (MethodCallExpr call : unit.findAll(MethodCallExpr.class)) {
            try {
                ResolvedMethodDeclaration method = call.resolve();

                resolvedCalls.add(
                        method.getQualifiedSignature()
                );

            } catch (RuntimeException ex) {
                resolvedCalls.add(
                        "UNRESOLVED: " + call.getNameAsString()
                );
            }
        }

        return resolvedCalls;
    }

    public List<String> resolveReferencedTypes(CompilationUnit unit) {

        List<String> resolvedTypes = new ArrayList<>();

        for (ClassOrInterfaceType type :
                unit.findAll(ClassOrInterfaceType.class)) {

            try {
                resolvedTypes.add(
                        type.resolve()
                                .asReferenceType()
                                .getQualifiedName()
                );

            } catch (RuntimeException ex) {
                resolvedTypes.add(
                        "UNRESOLVED: " + type.asString()
                );
            }
        }

        return resolvedTypes;
    }
}
