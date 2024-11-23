#!/usr/bin/env bash

# Author: Eshan Roy <m.eshanized@gmail.com>
# Description: This script configures GitHub user email and username.

set -e

# Function to display usage
usage() {
    echo "Usage: ${0##*/} [--email <email>] [--username <username>] [-h]"
    echo "    --email <email>       Set the GitHub user email."
    echo "    --username <username> Set the GitHub username."
    echo "    -h                    Display this help message."
    exit 1
}

# Parse command line arguments
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --email)
            EMAIL="$2"
            shift 2
            ;;
        --username)
            USERNAME="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown parameter passed: $1"
            usage
            ;;
    esac
done

# Prompt for email if not provided
if [ -z "$EMAIL" ]; then
    read -p "Enter your GitHub email: " EMAIL
fi

# Prompt for username if not provided
if [ -z "$USERNAME" ]; then
    read -p "Enter your GitHub username: " USERNAME
fi

# Set the Git configuration
git config --global user.email "$EMAIL"
git config --global user.name "$USERNAME"

# Confirmation message
echo "GitHub configuration updated:"
echo "  User Email: $EMAIL"
echo "  Username: $USERNAME"