import os
from dotenv import load_dotenv

load_dotenv()

# Blockchain Configuration
BLOCKCHAIN_CONFIG = {
    # Your deployed contract address on BSC Testnet
    "CONTRACT_ADDRESS": "0xD4AC352877064076621C6f6cF305aE3a8A16220e",
    
    # RPC URLs for different networks
    "RPC_URLS": {
        "bsc_testnet": "https://bnb-testnet.api.onfinality.io/public",
        "bsc_mainnet": "https://bsc-dataseed.binance.org/",
        "polygon": "https://polygon-rpc.com/",
        "ethereum": "https://mainnet.infura.io/v3/YOUR_INFURA_KEY",
        "avalanche": "https://api.avax.network/ext/bc/C/rpc",
        "arbitrum": "https://arb1.arbitrum.io/rpc"
    },
    
    # Current network - using BSC Testnet
    "CURRENT_NETWORK": "bsc_testnet",
    
    # Chain IDs
    "CHAIN_IDS": {
        "bsc_testnet": 97,
        "bsc_mainnet": 56,
        "polygon": 137,
        "ethereum": 1,
        "avalanche": 43114,
        "arbitrum": 42161
    },
    
    # Explorer URLs
    "EXPLORER_URLS": {
        "bsc_testnet": "https://testnet.bscscan.com",
        "bsc_mainnet": "https://bscscan.com",
        "polygon": "https://polygonscan.com",
        "ethereum": "https://etherscan.io",
        "avalanche": "https://snowtrace.io",
        "arbitrum": "https://arbiscan.io"
    },
    
    # Gas settings
    "GAS_SETTINGS": {
        "gas_limit": 500000,
        "max_gas_price": 20000000000,  # 20 Gwei for BSC Testnet
        "gas_buffer": 50000
    }
}

def get_blockchain_config():
    network = BLOCKCHAIN_CONFIG["CURRENT_NETWORK"]
    
    # Use the provided private key and wallet address as defaults
    default_private_key = "da3debbc37819e5dcd936640be0246ddaf3313ef3b9fdef977349e0bba1982f9"
    default_wallet_address = "0xb72e8049E0EE6018e49E9B3995e70b8FAf705897"
    
    return {
        "contract_address": BLOCKCHAIN_CONFIG["CONTRACT_ADDRESS"],
        "rpc_url": os.getenv("BLOCKCHAIN_RPC_URL", BLOCKCHAIN_CONFIG["RPC_URLS"][network]),
        "private_key": os.getenv("BLOCKCHAIN_PRIVATE_KEY", default_private_key),
        "wallet_address": os.getenv("BLOCKCHAIN_WALLET_ADDRESS", default_wallet_address),
        "chain_id": BLOCKCHAIN_CONFIG["CHAIN_IDS"][network],
        "gas_settings": BLOCKCHAIN_CONFIG["GAS_SETTINGS"],
        "network": network
    }

def get_network_info():
    network = BLOCKCHAIN_CONFIG["CURRENT_NETWORK"]
    return {
        "network": network,
        "explorer_url": BLOCKCHAIN_CONFIG["EXPLORER_URLS"][network],
        "chain_id": BLOCKCHAIN_CONFIG["CHAIN_IDS"][network]
    }