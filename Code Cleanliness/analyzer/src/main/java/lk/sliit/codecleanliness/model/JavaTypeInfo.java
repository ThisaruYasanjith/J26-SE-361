package lk.sliit.codecleanliness.model;

import java.nio.file.Path;
import java.util.List;

public record JavaTypeInfo(
        String qualifiedName,
        String kind,
        Path sourceFile,
        int line,
        List<MethodInfo> methods,
        List<FieldInfo> fields,
        List<String> extendedTypes,
        List<String> implementedTypes
) {
    public JavaTypeInfo {
        methods = List.copyOf(methods);
        fields = List.copyOf(fields);
        extendedTypes = List.copyOf(extendedTypes);
        implementedTypes = List.copyOf(implementedTypes);
    }

    public record MethodInfo(
            String name,
            String returnType,
            int parameterCount,
            int line
    ) {}

    public record FieldInfo(
            String name,
            String declaredType,
            int line
    ) {}
}
