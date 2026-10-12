package lk.sliit.codecleanliness.extraction;

import lk.sliit.codecleanliness.model.JavaTypeInfo;
import lk.sliit.codecleanliness.model.RepositoryParseResult;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.FieldDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.VariableDeclarator;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;

public class RepositoryStructureBuilder {

    public List<JavaTypeInfo> build(RepositoryParseResult result) {

        List<JavaTypeInfo> types = new ArrayList<>();

        for (Map.Entry<Path, CompilationUnit> entry :
                result.parsedFiles().entrySet()) {

            Path sourceFile = entry.getKey();
            CompilationUnit unit = entry.getValue();

            for (ClassOrInterfaceDeclaration declaration :
                    unit.findAll(ClassOrInterfaceDeclaration.class)) {

                List<JavaTypeInfo.MethodInfo> methods =
                        new ArrayList<>();

                for (MethodDeclaration method :
                        declaration.getMethods()) {

                    methods.add(new JavaTypeInfo.MethodInfo(
                            method.getNameAsString(),
                            method.getTypeAsString(),
                            method.getParameters().size(),
                            method.getBegin()
                                    .map(position -> position.line)
                                    .orElse(-1)
                    ));
                }

                List<JavaTypeInfo.FieldInfo> fields =
                        new ArrayList<>();

                for (FieldDeclaration field :
                        declaration.getFields()) {

                    for (VariableDeclarator variable :
                            field.getVariables()) {

                        fields.add(new JavaTypeInfo.FieldInfo(
                                variable.getNameAsString(),
                                variable.getTypeAsString(),
                                variable.getBegin()
                                        .map(position -> position.line)
                                        .orElse(-1)
                        ));
                    }
                }

                List<String> extendedTypes =
                        declaration.getExtendedTypes().stream()
                                .map(type -> type.asString())
                                .toList();

                List<String> implementedTypes =
                        declaration.getImplementedTypes().stream()
                                .map(type -> type.asString())
                                .toList();

                types.add(new JavaTypeInfo(
                        declaration.getFullyQualifiedName()
                                .orElse(declaration.getNameAsString()),
                        declaration.isInterface()
                                ? "INTERFACE"
                                : "CLASS",
                        sourceFile,
                        declaration.getBegin()
                                .map(position -> position.line)
                                .orElse(-1),
                        methods,
                        fields,
                        extendedTypes,
                        implementedTypes
                ));
            }
        }

        types.sort(Comparator
                .comparing(JavaTypeInfo::qualifiedName)
                .thenComparing(type -> type.sourceFile().toString()));

        return List.copyOf(types);
    }
}
