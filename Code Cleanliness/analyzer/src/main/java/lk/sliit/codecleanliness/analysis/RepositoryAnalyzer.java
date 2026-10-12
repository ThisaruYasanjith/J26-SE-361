package lk.sliit.codecleanliness.analysis;

import lk.sliit.codecleanliness.extraction.RepositoryRelationshipBuilder;
import lk.sliit.codecleanliness.extraction.RepositoryStructureBuilder;
import lk.sliit.codecleanliness.model.RepositoryAnalysisResult;
import lk.sliit.codecleanliness.model.RepositoryParseResult;
import lk.sliit.codecleanliness.parsing.JavaRepositoryParser;

import java.io.IOException;
import java.nio.file.Path;
import java.util.Objects;

public class RepositoryAnalyzer {

    private final JavaRepositoryParser parser;
    private final RepositoryStructureBuilder structureBuilder;
    private final RepositoryRelationshipBuilder relationshipBuilder;

    public RepositoryAnalyzer() {
        this(
                new JavaRepositoryParser(),
                new RepositoryStructureBuilder(),
                new RepositoryRelationshipBuilder()
        );
    }

    public RepositoryAnalyzer(
            JavaRepositoryParser parser,
            RepositoryStructureBuilder structureBuilder,
            RepositoryRelationshipBuilder relationshipBuilder) {

        this.parser = Objects.requireNonNull(parser);
        this.structureBuilder = Objects.requireNonNull(structureBuilder);
        this.relationshipBuilder = Objects.requireNonNull(
                relationshipBuilder
        );
    }

    public RepositoryAnalysisResult analyze(Path repositoryRoot)
            throws IOException {

        RepositoryParseResult parsed =
                parser.parseRepositoryWithSymbols(repositoryRoot);

        return new RepositoryAnalysisResult(
                parsed,
                structureBuilder.build(parsed),
                relationshipBuilder.build(parsed)
        );
    }
}
