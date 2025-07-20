import hashlib
import json
import asyncio
from typing import Dict, Optional, List
from web3 import Web3
from eth_account import Account
import os
from database import log_agent_activity
from blockchain_config import get_blockchain_config, get_network_info
from datetime import datetime

# Smart Contract ABI for ArticleHasher
ARTICLE_HASHER_ABI = [
    {
        "inputs": [
            {"internalType": "string", "name": "title", "type": "string"},
            {"internalType": "string", "name": "content", "type": "string"},
            {"internalType": "string", "name": "summary", "type": "string"}
        ],
        "name": "hashArticleContent",
        "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
        "stateMutability": "pure",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "string", "name": "source", "type": "string"},
            {"internalType": "string", "name": "originalLink", "type": "string"},
            {"internalType": "string", "name": "tags", "type": "string"},
            {"internalType": "uint256", "name": "authenticityScore", "type": "uint256"}
        ],
        "name": "hashArticleMetadata",
        "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
        "stateMutability": "pure",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "string", "name": "title", "type": "string"},
            {"internalType": "string", "name": "content", "type": "string"},
            {"internalType": "string", "name": "summary", "type": "string"},
            {"internalType": "string", "name": "source", "type": "string"},
            {"internalType": "string", "name": "originalLink", "type": "string"},
            {"internalType": "string", "name": "tags", "type": "string"},
            {"internalType": "uint256", "name": "authenticityScore", "type": "uint256"}
        ],
        "name": "storeArticleHash",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "contentHash", "type": "bytes32"}
        ],
        "name": "verifyArticleByHash",
        "outputs": [
            {"internalType": "bool", "name": "exists", "type": "bool"},
            {"internalType": "uint256", "name": "articleId", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "articleId", "type": "uint256"}
        ],
        "name": "getArticle",
        "outputs": [
            {
                "components": [
                    {"internalType": "bytes32", "name": "contentHash", "type": "bytes32"},
                    {"internalType": "bytes32", "name": "metadataHash", "type": "bytes32"},
                    {"internalType": "address", "name": "publisher", "type": "address"},
                    {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
                    {"internalType": "string", "name": "source", "type": "string"},
                    {"internalType": "bool", "name": "exists", "type": "bool"}
                ],
                "internalType": "struct ArticleHasher.ArticleRecord",
                "name": "record",
                "type": "tuple"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "count", "type": "uint256"}
        ],
        "name": "getRecentArticles",
        "outputs": [
            {"internalType": "uint256[]", "name": "recentArticles", "type": "uint256[]"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "getTotalArticles",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "articleCounter",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "articleId", "type": "uint256"},
            {"indexed": True, "internalType": "bytes32", "name": "contentHash", "type": "bytes32"},
            {"indexed": True, "internalType": "bytes32", "name": "metadataHash", "type": "bytes32"},
            {"indexed": False, "internalType": "address", "name": "publisher", "type": "address"},
            {"indexed": False, "internalType": "string", "name": "source", "type": "string"},
            {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"}
        ],
        "name": "ArticleHashed",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": False, "internalType": "uint256", "name": "existingArticleId", "type": "uint256"},
            {"indexed": False, "internalType": "bytes32", "name": "contentHash", "type": "bytes32"},
            {"indexed": False, "internalType": "address", "name": "attemptedPublisher", "type": "address"}
        ],
        "name": "DuplicateArticleDetected",
        "type": "event"
    }
]

class BlockchainHasher:
    def __init__(self, websocket_manager=None):
        self.websocket_manager = websocket_manager
        
        # Get blockchain configuration
        self.config = get_blockchain_config()
        self.network_info = get_network_info()
        
        self.contract_address = self.config["contract_address"]
        self.wallet_address = self.config["wallet_address"]
        self.rpc_url = self.config["rpc_url"]
        self.private_key = self.config["private_key"]
        self.chain_id = self.config["chain_id"]
        self.gas_settings = self.config["gas_settings"]
        
        # Initialize Web3 connection
        self.web3 = None
        self.contract = None
        self.account = None
        self._initialize_connection()
    
    def _initialize_connection(self):
        """Initialize blockchain connection"""
        if not self.private_key:
            print("Warning: No private key provided. Blockchain features will be limited.")
            return
        
        try:
            # Initialize Web3 with BSC Testnet
            self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))
            
            # Check connection
            if not self.web3.is_connected():
                print(f"Failed to connect to {self.network_info['network']} at {self.rpc_url}")
                return
            
            print(f"✅ Connected to {self.network_info['network']}")
            print(f"🌐 RPC URL: {self.rpc_url}")
            print(f"📄 Contract: {self.contract_address}")
            print(f"👛 Wallet: {self.wallet_address}")
            
            # Initialize account
            self.account = Account.from_key(self.private_key)
            
            # Verify wallet address matches
            if self.account.address.lower() != self.wallet_address.lower():
                print(f"⚠️  Warning: Private key address {self.account.address} doesn't match configured wallet {self.wallet_address}")
            
            # Initialize contract
            self.contract = self.web3.eth.contract(
                address=Web3.to_checksum_address(self.contract_address),
                abi=ARTICLE_HASHER_ABI
            )
            
            # Check account balance
            balance = self.web3.eth.get_balance(self.account.address)
            balance_bnb = self.web3.from_wei(balance, 'ether')
            print(f"💰 Wallet Balance: {balance_bnb:.4f} tBNB")
            
            if balance_bnb < 0.01:
                print("⚠️  Warning: Low balance. You may need more tBNB for gas fees.")
            
            print("🔗 Blockchain connection initialized successfully!")
            
        except Exception as e:
            print(f"❌ Blockchain connection error: {e}")
            self.web3 = None
            self.contract = None
            self.account = None
    
    def hash_article_content(self, title: str, content: str, summary: str = "") -> str:
        """Generate SHA-256 hash of article content (off-chain)"""
        combined_content = f"{title}{content}{summary}".encode('utf-8')
        return hashlib.sha256(combined_content).hexdigest()
    
    def hash_article_metadata(self, source: str, original_link: str, 
                            tags: str, authenticity_score: float) -> str:
        """Generate SHA-256 hash of article metadata (off-chain)"""
        metadata = f"{source}{original_link}{tags}{int(authenticity_score * 100)}"
        return hashlib.sha256(metadata.encode('utf-8')).hexdigest()
    
    async def check_blockchain_status(self) -> Dict:
        """Check blockchain connection and contract status"""
        if not self.web3 or not self.contract or not self.account:
            return {
                'connected': False,
                'error': 'Blockchain connection not initialized'
            }
        
        try:
            # Check connection
            latest_block = self.web3.eth.block_number
            balance = self.web3.eth.get_balance(self.account.address)
            balance_bnb = self.web3.from_wei(balance, 'ether')
            
            # Check contract
            total_articles = await self.get_total_articles_on_chain()
            
            return {
                'connected': True,
                'network': self.network_info['network'],
                'latest_block': latest_block,
                'wallet_address': self.account.address,
                'balance_bnb': float(balance_bnb),
                'contract_address': self.contract_address,
                'total_articles_on_chain': total_articles,
                'chain_id': self.chain_id
            }
            
        except Exception as e:
            return {
                'connected': False,
                'error': str(e)
            }
    
    async def store_article_on_blockchain(self, article_data: Dict) -> Dict:
        """Store article hash on the BSC testnet smart contract"""
        if not self.web3 or not self.contract or not self.account:
            return {
                'success': False,
                'error': 'Blockchain connection not available',
                'stored_on_chain': False
            }
        
        try:
            # Prepare data with length limits for gas optimization
            title = str(article_data.get('title', ''))[:300]  # Limit for gas
            content = str(article_data.get('content', ''))[:500]  # Limit for gas
            summary = str(article_data.get('summary', ''))[:200]
            source = str(article_data.get('source', ''))[:100]
            original_link = str(article_data.get('original_link', ''))[:300]
            tags = str(article_data.get('tags', ''))[:100]
            authenticity_score = int(float(article_data.get('authenticity_score', 0)) * 100)
            
            print(f"📝 Preparing to store article: {title[:50]}...")
            
            # Build transaction function
            function = self.contract.functions.storeArticleHash(
                title,
                content,
                summary,
                source,
                original_link,
                tags,
                authenticity_score
            )
            
            # Get current gas price
            gas_price = self.web3.eth.gas_price
            
            # Get gas estimate
            try:
                gas_estimate = function.estimate_gas({'from': self.account.address})
                gas_limit = min(gas_estimate + self.gas_settings['gas_buffer'], self.gas_settings['gas_limit'])
            except Exception as e:
                print(f"Gas estimation failed: {e}")
                gas_limit = self.gas_settings['gas_limit']
            
            print(f"⛽ Gas estimate: {gas_limit}")
            print(f"💸 Gas price: {self.web3.from_wei(gas_price, 'gwei')} Gwei")
            
            # Build transaction
            transaction = function.build_transaction({
                'from': self.account.address,
                'gas': gas_limit,
                'gasPrice': min(gas_price, self.gas_settings['max_gas_price']),
                'nonce': self.web3.eth.get_transaction_count(self.account.address),
                'chainId': self.chain_id
            })
            
            print(f"🔐 Signing transaction...")
            
            # Sign and send transaction
            signed_txn = self.account.sign_transaction(transaction)
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            print(f"📡 Transaction sent: {tx_hash.hex()}")
            print(f"🔗 BSC Testnet Explorer: https://testnet.bscscan.com/tx/{tx_hash.hex()}")
            
            # Wait for transaction receipt with timeout
            print("⏳ Waiting for transaction confirmation...")
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
            
            # Check if transaction was successful
            if receipt.status != 1:
                return {
                    'success': False,
                    'error': 'Transaction failed',
                    'transaction_hash': tx_hash.hex(),
                    'stored_on_chain': False
                }
            
            # Parse events to get article ID
            article_id = None
            for log in receipt.logs:
                try:
                    decoded = self.contract.events.ArticleHashed().process_log(log)
                    article_id = decoded.args.articleId
                    print(f"✅ Article stored with ID: {article_id}")
                    break
                except:
                    continue
            
            return {
                'success': True,
                'stored_on_chain': True,
                'transaction_hash': receipt.transactionHash.hex(),
                'block_number': receipt.blockNumber,
                'article_id': article_id,
                'gas_used': receipt.gasUsed,
                'effective_gas_price': receipt.effectiveGasPrice,
                'explorer_url': f"https://testnet.bscscan.com/tx/{receipt.transactionHash.hex()}"
            }
            
        except Exception as e:
            print(f"❌ Blockchain storage error: {e}")
            return {
                'success': False,
                'error': str(e),
                'stored_on_chain': False
            }
    
    async def verify_article_on_blockchain(self, content_hash: str) -> Dict:
        """Verify if article exists on blockchain"""
        if not self.web3 or not self.contract:
            return {'exists': False, 'error': 'Blockchain connection not available'}
        
        try:
            # Convert hash to bytes32 format
            if content_hash.startswith('0x'):
                hash_bytes = bytes.fromhex(content_hash[2:])
            else:
                hash_bytes = bytes.fromhex(content_hash)
            
            exists, article_id = self.contract.functions.verifyArticleByHash(hash_bytes).call()
            
            return {
                'exists': exists,
                'article_id': article_id if exists else None
            }
            
        except Exception as e:
            return {
                'exists': False,
                'error': str(e)
            }
    
    async def get_blockchain_article(self, article_id: int) -> Dict:
        """Get article details from blockchain"""
        if not self.web3 or not self.contract:
            return {'success': False, 'error': 'Blockchain connection not available'}
        
        try:
            article = self.contract.functions.getArticle(article_id).call()
            
            return {
                'success': True,
                'article': {
                    'content_hash': article[0].hex(),
                    'metadata_hash': article[1].hex(),
                    'publisher': article[2],
                    'timestamp': article[3],
                    'source': article[4],
                    'exists': article[5]
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_total_articles_on_chain(self) -> int:
        """Get total number of articles stored on blockchain"""
        if not self.web3 or not self.contract:
            return 0
        
        try:
            return self.contract.functions.getTotalArticles().call()
        except Exception as e:
            print(f"Error getting total articles: {e}")
            return 0
    
    def create_article_hash(self, article_data: Dict) -> Dict[str, str]:
        """Create comprehensive hash for an article"""
        title = article_data.get('title', '')
        content = article_data.get('content', '')
        summary = article_data.get('summary', '')
        source = article_data.get('source', '')
        original_link = article_data.get('original_link', '')
        tags = article_data.get('tags', '')
        authenticity_score = article_data.get('authenticity_score', 0.0)
        
        content_hash = self.hash_article_content(title, content, summary)
        metadata_hash = self.hash_article_metadata(source, original_link, tags, authenticity_score)
        combined_hash = hashlib.sha256(f"{content_hash}{metadata_hash}".encode('utf-8')).hexdigest()
        
        return {
            'content_hash': content_hash,
            'metadata_hash': metadata_hash,
            'combined_hash': combined_hash,
            'title_hash': hashlib.sha256(title.encode('utf-8')).hexdigest(),
            'timestamp': article_data.get('timestamp', '')
        }
    
    async def store_article_hash(self, article_data: Dict, pipeline_id: str = None) -> Dict:
        """Store article hash both off-chain and on-chain"""
        try:
            # Generate off-chain hashes
            hashes = self.create_article_hash(article_data)
            
            # Try to store on blockchain
            blockchain_result = await self.store_article_on_blockchain(article_data)
            
            # Create comprehensive result
            result = {
                'success': True,
                'hashes': hashes,
                'blockchain_result': blockchain_result,
                'stored_on_chain': blockchain_result.get('stored_on_chain', False),
                'network': self.network_info['network']
            }
            
            # Log the activity
            if pipeline_id:
                log_message = f"Article hashed: {article_data.get('title', '')[:50]}..."
                if blockchain_result.get('stored_on_chain'):
                    log_message += f" | BSC TX: {blockchain_result.get('transaction_hash', '')[:10]}..."
                
                await log_agent_activity(
                    pipeline_id, 
                    "Blockchain Hasher", 
                    log_message,
                    "INFO",
                    {
                        'content_hash': hashes['content_hash'],
                        'metadata_hash': hashes['metadata_hash'],
                        'article_id': article_data.get('id'),
                        'blockchain_stored': blockchain_result.get('stored_on_chain', False),
                        'transaction_hash': blockchain_result.get('transaction_hash'),
                        'network': self.network_info['network'],
                        'explorer_url': blockchain_result.get('explorer_url')
                    }
                )
            
            return result
            
        except Exception as e:
            if pipeline_id:
                await log_agent_activity(
                    pipeline_id, 
                    "Blockchain Hasher", 
                    f"Error hashing article: {str(e)}",
                    "ERROR"
                )
            
            return {
                'success': False,
                'error': str(e),
                'stored_on_chain': False
            }

# Integration function for your existing pipeline
async def integrate_blockchain_hashing(articles: List[Dict], pipeline_id: str, websocket_manager) -> List[Dict]:
    """Integrate blockchain hashing into the article processing pipeline"""
    hasher = BlockchainHasher(websocket_manager)
    
    # Check blockchain status
    status = await hasher.check_blockchain_status()
    
    # Send initial update with blockchain status
    await websocket_manager.broadcast(json.dumps({
        "agent": "Blockchain Hasher",
        "message": f"Starting blockchain hashing for {len(articles)} articles on {status.get('network', 'unknown')}...",
        "timestamp": datetime.now().isoformat(),
        "pipeline_id": pipeline_id,
        "data": {
            "blockchain_status": status,
            "total_articles": len(articles)
        }
    }))
    
    hashed_articles = []
    successful_blockchain_stores = 0
    
    for i, article in enumerate(articles):
        # Create article data structure for hashing
        article_data = {
            'id': article.get('id'),
            'title': article.get('original_title', article.get('title', '')),
            'content': article.get('generated_content', ''),
            'summary': article.get('summary', ''),
            'source': article.get('source', ''),
            'original_link': article.get('original_link', ''),
            'tags': '',  # Can be extracted from generated content if needed
            'authenticity_score': 0.75,  # Default or extract from authenticity_check
            'timestamp': article.get('processed_at', '')
        }
        
        # Store hash (both off-chain and on-chain)
        hash_result = await hasher.store_article_hash(article_data, pipeline_id)
        
        if hash_result['success']:
            # Add blockchain information to article
            article['blockchain_hashes'] = hash_result['hashes']
            article['blockchain_stored'] = hash_result.get('stored_on_chain', False)
            article['blockchain_network'] = hash_result.get('network', 'bsc_testnet')
            
            if hash_result.get('stored_on_chain'):
                successful_blockchain_stores += 1
                article['blockchain_transaction'] = hash_result['blockchain_result']
        
        hashed_articles.append(article)
        
        # Send progress update
        await websocket_manager.broadcast(json.dumps({
            "agent": "Blockchain Hasher",
            "message": f"Processed {i+1}/{len(articles)} articles",
            "timestamp": datetime.now().isoformat(),
            "pipeline_id": pipeline_id,
            "data": {
                "progress": f"{i+1}/{len(articles)}",
                "blockchain_stores": successful_blockchain_stores,
                "current_article": article_data.get('title', '')[:50]
            }
        }))
    
    # Send completion update
    success_rate = (successful_blockchain_stores/len(articles)*100) if articles else 0
    await websocket_manager.broadcast(json.dumps({
        "agent": "Blockchain Hasher",
        "message": f"Blockchain hashing completed! {successful_blockchain_stores}/{len(articles)} stored on BSC Testnet",
        "timestamp": datetime.now().isoformat(),
        "pipeline_id": pipeline_id,
        "data": {
            "total_articles": len(articles),
            "blockchain_stores": successful_blockchain_stores,
            "success_rate": f"{success_rate:.1f}%",
            "network": "BSC Testnet",
            "explorer": "https://testnet.bscscan.com"
        }
    }))
    
    return hashed_articles