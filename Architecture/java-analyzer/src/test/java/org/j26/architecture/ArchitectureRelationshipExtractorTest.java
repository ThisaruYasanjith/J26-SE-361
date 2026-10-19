package org.j26.architecture;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.javaparser.JavaParser;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.ast.CompilationUnit;
import org.j26.architecture.model.ComponentInfo;
import org.j26.architecture.model.RelationshipInfo;
import org.j26.architecture.model.RelationshipType;
import org.j26.architecture.model.SourceLocation;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ArchitectureRelationshipExtractorTest {
    @TempDir
    Path project;

    private final JavaProjectScanner scanner = new JavaProjectScanner();

    @Test
    void extractsExplicitInternalImportsForEachTopLevelSource() throws IOException {
        type("demo.api", "Target", "public class Target {}");
        source("import demo.api.Target; class Source {} interface Other {}");

        List<RelationshipInfo> relationships = scanner.scan(project).relationships();

        assertEquals(Set.of("demo.Source IMPORTS demo.api.Target", "demo.Other IMPORTS demo.api.Target"), signatures(relationships));
    }

    @ParameterizedTest
    @ValueSource(strings = {"java.util", "javax.example", "jakarta.example", "org.springframework.example", "org.slf4j"})
    void externalImportsCannotFallBackToSameNamedProjectTypes(String externalPackage) throws IOException {
        type("demo", "Target", "class Target {}");
        source("import " + externalPackage + ".Target; class Source { Target target; void run() { target.call(); } }");

        assertTrue(scanner.scan(project).relationships().isEmpty());
    }

    @Test
    void skipsStaticAndWildcardImportsAndUnresolvedWildcardTypes() throws IOException {
        type("demo.api", "Target", "public class Target {}");
        source("import static demo.api.Target.VALUE; import demo.api.*; class Source { Target target; }");

        assertTrue(scanner.scan(project).relationships().isEmpty());
    }

    @Test
    void doesNotGuessGloballyUniqueSimpleNames() throws IOException {
        type("other", "Target", "public class Target {}");
        source("class Source { Target target; void run() { target.call(); } }");

        assertTrue(scanner.scan(project).relationships().isEmpty());
    }

    @Test
    void resolvesExplicitImportsAndFullyQualifiedReferencesWithoutNameCollisions() throws IOException {
        type("one", "Target", "public class Target {}");
        type("two", "Target", "public class Target {}");
        source("""
                import one.Target;
                class Source {
                    Target first;
                    two.Target second;
                    void run() { first.call(); second.call(); }
                }
                """);

        Set<String> edges = signatures(scanner.scan(project).relationships());

        assertEquals(Set.of("demo.Source IMPORTS one.Target", "demo.Source DEPENDS_ON one.Target",
                "demo.Source DEPENDS_ON two.Target", "demo.Source CALLS one.Target", "demo.Source CALLS two.Target"), edges);
    }

    @Test
    void skipsAmbiguousExplicitImports() throws IOException {
        type("one", "Target", "public class Target {}");
        type("two", "Target", "public class Target {}");
        source("import one.Target; import two.Target; class Source { Target target; }");

        List<RelationshipInfo> edges = scanner.scan(project).relationships();

        assertEquals(2, edges.size());
        assertTrue(edges.stream().allMatch(edge -> edge.relationship() == RelationshipType.IMPORTS));
    }

    @Test
    void extractsConstructorParameterDependencies() throws IOException {
        target("Target");
        target("Gateway");
        source("class Source { Source(Target target, Gateway gateway, String label) {} }");

        assertEquals(Set.of("demo.Source DEPENDS_ON demo.Target", "demo.Source DEPENDS_ON demo.Gateway"),
                signatures(scanner.scan(project).relationships()));
    }

    @Test
    void extractsFieldDependenciesIncludingGenericArgumentsAndArrays() throws IOException {
        target("Target");
        target("Gateway");
        source("""
                import java.util.List;
                class Source {
                    Target target;
                    Gateway[] gateways;
                    List<? extends Target> targets;
                    List<? super Gateway> moreGateways;
                    int count;
                }
                """);

        assertEquals(Set.of("demo.Source DEPENDS_ON demo.Target", "demo.Source DEPENDS_ON demo.Gateway"),
                signatures(scanner.scan(project).relationships()));
    }

    @Test
    void extractsObjectCreationAndDeduplicatesInjectionAndRepeatedCalls() throws IOException {
        target("Target");
        source("""
                class Source {
                    private Target target;
                    Source(Target target) { this.target = target; }
                    void run() { new Target(); new Target(); target.call(); target.call(); }
                }
                """);

        assertEquals(Set.of("demo.Source DEPENDS_ON demo.Target", "demo.Source CALLS demo.Target"),
                signatures(scanner.scan(project).relationships()));
    }

    @Test
    void objectCreationDoesNotCreateExternalDependencies() throws IOException {
        target("Target");
        source("class Source { void run() { new Target(); new java.util.ArrayList<>(); new External(); } }");

        assertEquals(Set.of("demo.Source DEPENDS_ON demo.Target"), signatures(scanner.scan(project).relationships()));
    }

    @Test
    void identifiesCallsFromFieldsConstructorParametersMethodParametersAndLocals() throws IOException {
        for (String name : List.of("FieldTarget", "ConstructorTarget", "ParameterTarget", "LocalTarget", "InferredTarget")) {
            target(name);
        }
        source("""
                class Source {
                    FieldTarget field;
                    Source(ConstructorTarget injected) { injected.call(); }
                    void run(ParameterTarget parameter) {
                        LocalTarget local = null;
                        var inferred = new InferredTarget();
                        field.call(); parameter.call(); local.call(); inferred.call();
                    }
                }
                """);

        Set<String> callTargets = scanner.scan(project).relationships().stream()
                .filter(edge -> edge.relationship() == RelationshipType.CALLS).map(RelationshipInfo::target).collect(Collectors.toSet());

        assertEquals(Set.of("demo.FieldTarget", "demo.ConstructorTarget", "demo.ParameterTarget", "demo.LocalTarget", "demo.InferredTarget"), callTargets);
    }

    @Test
    void skipsUnknownChainedAndUnscopedCalls() throws IOException {
        target("Target");
        source("class Source { void run() { unknown.call(); factory.make().call(); localCall(); new External().call(); } }");

        assertTrue(scanner.scan(project).relationships().isEmpty());
    }

    @Test
    void thisFieldRemainsKnownWhenAParameterShadowsItsName() throws IOException {
        target("Target");
        source("class Source { Target target; void run(Object target) { target.toString(); this.target.call(); } }");

        RelationshipInfo call = edge(scanner.scan(project).relationships(), "demo.Source", "demo.Target", RelationshipType.CALLS);

        assertTrue(call.sourceLocation() != null);
    }

    @Test
    void unknownParametersAndLocalsShadowFields() throws IOException {
        target("Target");
        source("""
                class Source {
                    Target target;
                    void first(Object target) { target.toString(); }
                    void second() { Object target = null; target.toString(); }
                    void third() { var target = unknown(); target.call(); }
                }
                """);

        assertTrue(scanner.scan(project).relationships().stream().noneMatch(edge -> edge.relationship() == RelationshipType.CALLS));
    }

    @Test
    void observesBlockScopesAndDeclarationOrderForLocalBindings() throws IOException {
        target("FieldTarget");
        target("LocalTarget");
        source("""
                class Source {
                    FieldTarget target;
                    void run() {
                        target.call();
                        { Object target = null; target.toString(); }
                        LocalTarget target = null;
                        target.call();
                    }
                }
                """);

        Set<String> targets = scanner.scan(project).relationships().stream()
                .filter(edge -> edge.relationship() == RelationshipType.CALLS).map(RelationshipInfo::target).collect(Collectors.toSet());

        assertEquals(Set.of("demo.FieldTarget", "demo.LocalTarget"), targets);
    }

    @Test
    void inferredLambdaParametersDoNotFallBackToFields() throws IOException {
        target("Target");
        source("""
                class Source {
                    Target target;
                    void run() { consume(target -> target.call()); }
                }
                """);

        assertTrue(scanner.scan(project).relationships().stream().noneMatch(edge -> edge.relationship() == RelationshipType.CALLS));
    }

    @Test
    void identifiesExplicitLambdaLoopAndResourceBindings() throws IOException {
        target("LambdaTarget");
        target("LoopTarget");
        target("ResourceTarget");
        source("""
                class Source {
                    void run() {
                        consume((LambdaTarget lambda) -> lambda.call());
                        for (LoopTarget loop : unknown()) { loop.call(); }
                        for (LoopTarget loop = null; unknown(); ) { loop.call(); }
                        try (ResourceTarget resource = null) { resource.call(); }
                    }
                }
                """);

        assertEquals(Set.of("demo.Source CALLS demo.LambdaTarget", "demo.Source CALLS demo.LoopTarget", "demo.Source CALLS demo.ResourceTarget"),
                signatures(scanner.scan(project).relationships()));
    }

    @Test
    void catchAndPatternBindingsDoNotFallBackToFields() throws IOException {
        target("Target");
        source("""
                class Source {
                    Target target;
                    void run(Object value) {
                        try { unknown(); } catch (Exception target) { target.toString(); }
                        if (value instanceof Object target) { target.toString(); }
                    }
                }
                """);

        assertTrue(scanner.scan(project).relationships().stream().noneMatch(edge -> edge.relationship() == RelationshipType.CALLS));
    }

    @Test
    void genericContainersAreNotMistakenForTheirProjectTypeArgumentsInCalls() throws IOException {
        target("Target");
        source("import java.util.List; class Source { List<Target> targets; void run() { targets.size(); } }");

        assertEquals(Set.of("demo.Source DEPENDS_ON demo.Target"), signatures(scanner.scan(project).relationships()));
    }

    @Test
    void supportsExplicitCastAndObjectCreationReceivers() throws IOException {
        target("Target");
        target("Gateway");
        source("class Source { void run(Object value) { ((Target) value).call(); new Gateway().call(); } }");

        assertEquals(Set.of("demo.Source CALLS demo.Target", "demo.Source CALLS demo.Gateway", "demo.Source DEPENDS_ON demo.Gateway"),
                signatures(scanner.scan(project).relationships()));
    }

    @Test
    void extractsExtendsImplementsAndInterfaceExtendsFromExistingMetadata() throws IOException {
        type("demo", "Parent", "class Parent {}");
        type("demo.api", "Auditable", "public interface Auditable {}");
        type("demo", "Trackable", "interface Trackable {}");
        source("""
                import demo.api.Auditable;
                class Source extends Parent implements Auditable, Trackable {}
                interface Combined extends Auditable, Trackable {}
                """);

        Set<String> edges = signatures(scanner.scan(project).relationships());

        assertTrue(edges.containsAll(Set.of("demo.Source EXTENDS demo.Parent", "demo.Source IMPLEMENTS demo.api.Auditable",
                "demo.Source IMPLEMENTS demo.Trackable", "demo.Combined EXTENDS demo.api.Auditable", "demo.Combined EXTENDS demo.Trackable")));
        assertTrue(edges.stream().noneMatch(edge -> edge.contains("CONTAINS")));
    }

    @Test
    void preservesSourceSpansForImportsFieldsCallsAndInheritance() throws IOException {
        target("Target");
        type("demo", "Api", "interface Api {}");
        type("demo.api", "Imported", "public class Imported {}");
        source("""
                import demo.api.Imported;
                class Source extends Target implements Api {
                    private Target target;
                    void run() {
                        target.call();
                    }
                }
                """);

        List<RelationshipInfo> edges = scanner.scan(project).relationships();

        assertEquals(new SourceLocation(2, 2), edge(edges, "demo.Source", "demo.api.Imported", RelationshipType.IMPORTS).sourceLocation());
        assertEquals(new SourceLocation(3, 3), edge(edges, "demo.Source", "demo.Target", RelationshipType.EXTENDS).sourceLocation());
        assertEquals(new SourceLocation(3, 3), edge(edges, "demo.Source", "demo.Api", RelationshipType.IMPLEMENTS).sourceLocation());
        assertEquals(new SourceLocation(4, 4), edge(edges, "demo.Source", "demo.Target", RelationshipType.DEPENDS_ON).sourceLocation());
        assertEquals(new SourceLocation(6, 6), edge(edges, "demo.Source", "demo.Target", RelationshipType.CALLS).sourceLocation());
    }

    @Test
    void deduplicationKeepsTheEarliestKnownDependencyReference() throws IOException {
        target("Target");
        source("""
                class Source {
                    Source(Target target) {}
                    Target field;
                    void run() { new Target(); }
                }
                """);

        List<RelationshipInfo> edges = scanner.scan(project).relationships();

        assertEquals(1, edges.size());
        assertEquals(new SourceLocation(3, 3), edges.get(0).sourceLocation());
    }

    @Test
    void preservesMultilineConstructorParameterLocations() throws IOException {
        target("Target");
        source("class Source {\n Source(\n Target\n target) {}\n}");

        RelationshipInfo dependency = scanner.scan(project).relationships().get(0);

        assertEquals(new SourceLocation(4, 4), dependency.sourceLocation());
    }

    @Test
    void excludesFrameworkTargetsEvenIfReservedPackagesAppearInTheSourceTree() throws IOException {
        type("org.springframework.example", "Target", "public class Target {}");
        source("import org.springframework.example.Target; class Source { Target field; }");

        assertTrue(scanner.scan(project).relationships().isEmpty());
    }

    @Test
    void typeParametersAndNestedTypesDoNotResolveToSameNamedProjectTypes() throws IOException {
        target("Target");
        source("""
                class Source<Target> { Target field; void run(Target parameter) { field.call(); parameter.call(); } }
                class Another { class Target {} Target field; }
                class Third { <Target> void run(Target parameter) { parameter.call(); } }
                """);

        assertTrue(scanner.scan(project).relationships().isEmpty());
    }

    @Test
    void nestedAndAnonymousClassBodiesDoNotLeakRelationshipsToTheOuterClass() throws IOException {
        target("Target");
        source("""
                class Source {
                    class Nested { Target field; Nested(Target target) {} void run() { new Target(); } }
                    Object anonymous = new Object() { Target field; void run() { new Target(); } };
                }
                """);

        assertTrue(scanner.scan(project).relationships().isEmpty());
    }

    @Test
    void anonymousConstructorArgumentsStillBelongToTheOuterClass() throws IOException {
        target("ConstructorTarget");
        target("HiddenTarget");
        source("""
                class Source {
                    Object value = new Object(new ConstructorTarget()) {
                        void run() { new HiddenTarget(); }
                    };
                }
                """);

        assertEquals(Set.of("demo.Source DEPENDS_ON demo.ConstructorTarget"), signatures(scanner.scan(project).relationships()));
    }

    @Test
    void parseFailuresCannotBecomeRelationshipTargetsAndDoNotStopValidFiles() throws IOException {
        target("Target");
        type("demo", "ABroken", "class ABroken { void broken( }");
        source("class Source { Target target; ABroken broken; void run() { target.call(); } }");

        JavaProjectScanner.ScanResult result = scanner.scan(project);

        assertEquals(3, result.javaFiles().size());
        assertEquals(2, result.successfullyParsed());
        assertEquals(1, result.parseFailures().size());
        assertEquals(2, result.extractedEntityCount());
        assertEquals(2, result.extractedRelationshipCount());
        assertEquals(Set.of("demo.Source DEPENDS_ON demo.Target", "demo.Source CALLS demo.Target"), signatures(result.relationships()));
    }

    @Test
    void repeatedScansHaveStableRelationshipsAndOnlyKnownEndpoints() throws IOException {
        target("Target");
        source("class Source { Target target; void run() { target.call(); } }");

        JavaProjectScanner.ScanResult first = scanner.scan(project);
        JavaProjectScanner.ScanResult second = scanner.scan(project);
        Set<String> names = first.components().stream().map(ComponentInfo::name).collect(Collectors.toSet());

        assertEquals(first.relationships(), second.relationships());
        assertTrue(first.relationships().stream().allMatch(edge -> names.contains(edge.source()) && names.contains(edge.target())));
    }

    @Test
    void missingRangesAreOmittedAndReplacedByAKnownOccurrenceWhenAvailable() {
        JavaParser parser = new JavaParser(new ParserConfiguration().setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_17));
        CompilationUnit unit = parser.parse("class Source { Target field; Source(Target target) {} } class Target {}").getResult().orElseThrow();
        List<ComponentInfo> components = new ArchitectureEntityExtractor().extract(unit, project, project.resolve("Source.java"));
        unit.getType(0).asClassOrInterfaceDeclaration().getFieldByName("field").orElseThrow()
                .getVariable(0).getType().setRange(null);

        List<RelationshipInfo> edges = new ArchitectureRelationshipExtractor().extract(List.of(unit), components);

        assertEquals(1, edges.size());
        assertEquals(new SourceLocation(1, 1), edges.get(0).sourceLocation());
        unit.getType(0).asClassOrInterfaceDeclaration().getConstructors().get(0).getParameter(0).getType().setRange(null);
        assertNull(new ArchitectureRelationshipExtractor().extract(List.of(unit), components).get(0).sourceLocation());
    }

    @Test
    void relationshipJsonUsesContractNamesAndOmitsMissingLocations() {
        ObjectMapper mapper = new ObjectMapper();
        JsonNode located = mapper.valueToTree(new RelationshipInfo("demo.Source", "demo.Target", RelationshipType.DEPENDS_ON, new SourceLocation(2, 3)));
        JsonNode unlocated = mapper.valueToTree(new RelationshipInfo("demo.Source", "demo.Target", RelationshipType.CALLS, null));
        Set<String> fields = new HashSet<>();
        located.fieldNames().forEachRemaining(fields::add);

        assertEquals(Set.of("source", "target", "relationship", "source_location"), fields);
        assertEquals("DEPENDS_ON", located.get("relationship").asText());
        assertEquals(2, located.get("source_location").get("start_line").asInt());
        assertEquals(3, located.get("source_location").get("end_line").asInt());
        assertEquals(3, unlocated.size());
        assertFalse(unlocated.has("source_location"));
    }

    @Test
    void researchStyleFixtureProvidesTheExpectedDependenciesAndCliSummary() throws IOException {
        type("demo", "PaymentRepository", "interface PaymentRepository {}");
        type("demo", "PaymentGateway", "interface PaymentGateway {}");
        type("demo", "PaymentService", """
                class PaymentService {
                    PaymentRepository repository;
                    PaymentGateway gateway;
                    PaymentService(PaymentRepository repository, PaymentGateway gateway) {}
                    void pay() { gateway.charge(); repository.save(); }
                }
                """);
        type("demo", "PaymentController", "class PaymentController { PaymentService service; void pay() { service.pay(); } }");
        type("demo", "ReportingService", "class ReportingService { ReportingService(PaymentGateway gateway) { gateway.charge(); } }");
        type("demo", "AdminController", "class AdminController { PaymentRepository repository; void report() { repository.findAll(); } }");

        JavaProjectScanner.ScanResult result = scanner.scan(project);

        assertEquals(6, result.extractedEntityCount());
        assertEquals(10, result.extractedRelationshipCount());
        assertTrue(signatures(result.relationships()).containsAll(Set.of(
                "demo.PaymentController DEPENDS_ON demo.PaymentService",
                "demo.PaymentService DEPENDS_ON demo.PaymentRepository",
                "demo.PaymentService DEPENDS_ON demo.PaymentGateway",
                "demo.ReportingService DEPENDS_ON demo.PaymentGateway",
                "demo.AdminController DEPENDS_ON demo.PaymentRepository")));
        ByteArrayOutputStream messages = new ByteArrayOutputStream();
        try (PrintStream output = new PrintStream(messages, true, StandardCharsets.UTF_8)) {
            assertEquals(0, AnalyzerMain.run(new String[]{project.toString()}, output, output));
        }
        String text = messages.toString(StandardCharsets.UTF_8);
        assertTrue(text.contains("Architecture relationships extracted: 10"));
        assertTrue(text.contains("PaymentService CALLS PaymentGateway"));
        assertTrue(text.contains("PaymentController DEPENDS_ON PaymentService"));
        assertFalse(Files.exists(project.resolve("project_context.json")));
    }

    private Set<String> signatures(List<RelationshipInfo> relationships) {
        return relationships.stream().map(edge -> edge.source() + " " + edge.relationship() + " " + edge.target()).collect(Collectors.toSet());
    }

    private RelationshipInfo edge(List<RelationshipInfo> edges, String source, String target, RelationshipType type) {
        return edges.stream().filter(edge -> edge.source().equals(source) && edge.target().equals(target) && edge.relationship() == type)
                .findFirst().orElseThrow(() -> new AssertionError("Missing edge " + source + " " + type + " " + target));
    }

    private void target(String name) throws IOException {
        type("demo", name, "class " + name + " {}");
    }

    private void source(String declaration) throws IOException {
        type("demo", "Source", declaration);
    }

    private void type(String packageName, String name, String declaration) throws IOException {
        Path file = project.resolve("src/main/java/" + packageName.replace('.', '/') + "/" + name + ".java");
        Files.createDirectories(file.getParent());
        Files.writeString(file, "package " + packageName + ";\n" + declaration, StandardCharsets.UTF_8);
    }
}
