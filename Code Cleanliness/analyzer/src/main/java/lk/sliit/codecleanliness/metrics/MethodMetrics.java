package lk.sliit.codecleanliness.metrics;

public record MethodMetrics(
        String methodName,
        int line,
        int ncss,
        int cyclomaticComplexity
) {}
