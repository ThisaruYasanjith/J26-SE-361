package lk.sliit.codecleanliness;

public record MethodMetrics(
        String methodName,
        int line,
        int ncss,
        int cyclomaticComplexity
) {}