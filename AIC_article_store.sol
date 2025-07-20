// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title ArticleHasher
 * @dev Smart contract for hashing and storing article metadata on blockchain
 * @notice This contract provides secure hashing for news articles with timestamping
 */
contract ArticleHasher {
    
    // Struct to store article metadata
    struct ArticleRecord {
        bytes32 contentHash;        // Hash of the article content
        bytes32 metadataHash;       // Hash of metadata (title, source, etc.)
        address publisher;          // Address of the publisher
        uint256 timestamp;          // When the article was published
        string source;              // News source identifier
        bool exists;                // Flag to check if record exists
    }
    
    // Mapping from article ID to article record
    mapping(uint256 => ArticleRecord) public articles;
    
    // Mapping from content hash to article ID (for duplicate detection)
    mapping(bytes32 => uint256) public contentHashToId;
    
    // Mapping from publisher to their article count
    mapping(address => uint256) public publisherArticleCount;
    
    // Array to store all article IDs
    uint256[] public articleIds;
    
    // Current article counter
    uint256 public articleCounter;
    
    // Events
    event ArticleHashed(
        uint256 indexed articleId,
        bytes32 indexed contentHash,
        bytes32 indexed metadataHash,
        address publisher,
        string source,
        uint256 timestamp
    );
    
    event DuplicateArticleDetected(
        uint256 existingArticleId,
        bytes32 contentHash,
        address attemptedPublisher
    );
    
    /**
     * @dev Hash article content using keccak256
     * @param title Article title
     * @param content Article content
     * @param summary Article summary
     * @return Hash of the combined content
     */
    function hashArticleContent(
        string memory title,
        string memory content,
        string memory summary
    ) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(title, content, summary));
    }
    
    /**
     * @dev Hash article metadata
     * @param source News source
     * @param originalLink Original article link
     * @param tags Article tags
     * @param authenticityScore Authenticity score
     * @return Hash of the metadata
     */
    function hashArticleMetadata(
        string memory source,
        string memory originalLink,
        string memory tags,
        uint256 authenticityScore
    ) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(
            source,
            originalLink,
            tags,
            authenticityScore
        ));
    }
    
    /**
     * @dev Create a comprehensive hash for the entire article
     * @param title Article title
     * @param content Article content
     * @param summary Article summary
     * @param source News source
     * @param originalLink Original article link
     * @param tags Article tags
     * @param authenticityScore Authenticity score
     * @return Combined hash of content and metadata
     */
    function createArticleHash(
        string memory title,
        string memory content,
        string memory summary,
        string memory source,
        string memory originalLink,
        string memory tags,
        uint256 authenticityScore
    ) public pure returns (bytes32, bytes32, bytes32) {
        bytes32 contentHash = hashArticleContent(title, content, summary);
        bytes32 metadataHash = hashArticleMetadata(source, originalLink, tags, authenticityScore);
        bytes32 combinedHash = keccak256(abi.encodePacked(contentHash, metadataHash));
        
        return (contentHash, metadataHash, combinedHash);
    }
    
    /**
     * @dev Store article hash on blockchain with duplicate detection
     * @param title Article title
     * @param content Article content
     * @param summary Article summary
     * @param source News source
     * @param originalLink Original article link
     * @param tags Article tags
     * @param authenticityScore Authenticity score
     * @return Article ID if successful, 0 if duplicate
     */
    function storeArticleHash(
        string memory title,
        string memory content,
        string memory summary,
        string memory source,
        string memory originalLink,
        string memory tags,
        uint256 authenticityScore
    ) public returns (uint256) {
        (bytes32 contentHash, bytes32 metadataHash,) = createArticleHash(
            title, content, summary, source, originalLink, tags, authenticityScore
        );
        
        // Check for duplicate content
        if (contentHashToId[contentHash] != 0) {
            emit DuplicateArticleDetected(contentHashToId[contentHash], contentHash, msg.sender);
            return 0; // Return 0 for duplicate
        }
        
        // Increment counter and create new article record
        articleCounter++;
        uint256 newArticleId = articleCounter;
        
        articles[newArticleId] = ArticleRecord({
            contentHash: contentHash,
            metadataHash: metadataHash,
            publisher: msg.sender,
            timestamp: block.timestamp,
            source: source,
            exists: true
        });
        
        // Update mappings
        contentHashToId[contentHash] = newArticleId;
        publisherArticleCount[msg.sender]++;
        articleIds.push(newArticleId);
        
        emit ArticleHashed(
            newArticleId,
            contentHash,
            metadataHash,
            msg.sender,
            source,
            block.timestamp
        );
        
        return newArticleId;
    }
    
    /**
     * @dev Verify if an article exists by content hash
     * @param contentHash Hash of the article content
     * @return exists Whether the article exists
     * @return articleId The ID of the article (0 if doesn't exist)
     */
    function verifyArticleByHash(bytes32 contentHash) 
        public 
        view 
        returns (bool exists, uint256 articleId) 
    {
        articleId = contentHashToId[contentHash];
        exists = articleId != 0;
        return (exists, articleId);
    }
    
    /**
     * @dev Get article record by ID
     * @param articleId The article ID
     * @return record The complete article record
     */
    function getArticle(uint256 articleId) 
        public 
        view 
        returns (ArticleRecord memory record) 
    {
        require(articles[articleId].exists, "Article does not exist");
        return articles[articleId];
    }
    
    /**
     * @dev Get articles published by a specific address
     * @param publisher The publisher address
     * @return articleList Array of article IDs published by the address
     */
    function getArticlesByPublisher(address publisher) 
        public 
        view 
        returns (uint256[] memory articleList) 
    {
        uint256 count = publisherArticleCount[publisher];
        articleList = new uint256[](count);
        uint256 index = 0;
        
        for (uint256 i = 1; i <= articleCounter; i++) {
            if (articles[i].exists && articles[i].publisher == publisher) {
                articleList[index] = i;
                index++;
                if (index >= count) break;
            }
        }
        
        return articleList;
    }
    
    /**
     * @dev Get recent articles (last N articles)
     * @param count Number of recent articles to retrieve
     * @return recentArticles Array of recent article IDs
     */
    function getRecentArticles(uint256 count) 
        public 
        view 
        returns (uint256[] memory recentArticles) 
    {
        uint256 totalArticles = articleIds.length;
        uint256 returnCount = count > totalArticles ? totalArticles : count;
        
        recentArticles = new uint256[](returnCount);
        
        for (uint256 i = 0; i < returnCount; i++) {
            recentArticles[i] = articleIds[totalArticles - 1 - i];
        }
        
        return recentArticles;
    }
    
    /**
     * @dev Get total number of articles
     * @return Total article count
     */
    function getTotalArticles() public view returns (uint256) {
        return articleCounter;
    }
    
    /**
     * @dev Batch verify multiple content hashes
     * @param contentHashes Array of content hashes to verify
     * @return results Array of verification results
     */
    function batchVerifyArticles(bytes32[] memory contentHashes) 
        public 
        view 
        returns (bool[] memory results) 
    {
        results = new bool[](contentHashes.length);
        
        for (uint256 i = 0; i < contentHashes.length; i++) {
            results[i] = contentHashToId[contentHashes[i]] != 0;
        }
        
        return results;
    }
}