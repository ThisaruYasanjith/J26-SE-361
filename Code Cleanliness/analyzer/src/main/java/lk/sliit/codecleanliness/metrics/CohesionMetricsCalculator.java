package lk.sliit.codecleanliness.metrics;

import lk.sliit.codecleanliness.model.MethodUsageInfo;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CohesionMetricsCalculator {

    public CohesionMetrics calculate(
            String qualifiedClassName,
            List<MethodUsageInfo> allUsages) {

        List<MethodUsageInfo> methods = allUsages.stream()
                .filter(m -> qualifiedClassName.equals(m.ownerType()))
                .toList();

        int n = methods.size();

        if (n == 0) {
            return new CohesionMetrics(
                    qualifiedClassName, 0, 0, 0, 0.0, 0
            );
        }

        int possiblePairs = n * (n - 1) / 2;
        int connectedPairs = 0;

        // Undirected graph for LCOM4 connected components.
        List<Set<Integer>> graph = new ArrayList<>();

        for (int i = 0; i < n; i++) {
            graph.add(new HashSet<>());
        }

        Map<String, Integer> methodIndex = new HashMap<>();

        for (int i = 0; i < n; i++) {
            // Preliminary signature convention. Verified against
            // simple non-overloaded calls in our initial tests.
            String signature = qualifiedClassName + "."
                    + methods.get(i).methodSignature();

            methodIndex.put(signature, i);
        }

        for (int i = 0; i < n; i++) {

            Set<String> firstFields =
                    new HashSet<>(methods.get(i).accessedFields());

            for (int j = i + 1; j < n; j++) {

                Set<String> secondFields =
                        new HashSet<>(methods.get(j).accessedFields());

                secondFields.retainAll(firstFields);

                if (!secondFields.isEmpty()) {
                    connectedPairs++;
                    connect(graph, i, j);
                }
            }

            for (String called : methods.get(i).calledMethods()) {

                Integer targetIndex = methodIndex.get(called);

                if (targetIndex != null && targetIndex != i) {
                    connect(graph, i, targetIndex);
                }
            }
        }

        double tcc = possiblePairs == 0
                ? 0.0
                : (double) connectedPairs / possiblePairs;

        boolean[] visited = new boolean[n];
        int components = 0;

        for (int i = 0; i < n; i++) {
            if (!visited[i]) {
                components++;
                visitComponent(i, graph, visited);
            }
        }

        return new CohesionMetrics(
                qualifiedClassName,
                n,
                possiblePairs,
                connectedPairs,
                tcc,
                components
        );
    }

    private void connect(
            List<Set<Integer>> graph,
            int first,
            int second) {

        graph.get(first).add(second);
        graph.get(second).add(first);
    }

    private void visitComponent(
            int start,
            List<Set<Integer>> graph,
            boolean[] visited) {

        java.util.ArrayDeque<Integer> queue =
                new java.util.ArrayDeque<>();

        queue.add(start);
        visited[start] = true;

        while (!queue.isEmpty()) {
            int current = queue.remove();

            for (int neighbor : graph.get(current)) {
                if (!visited[neighbor]) {
                    visited[neighbor] = true;
                    queue.add(neighbor);
                }
            }
        }
    }
}