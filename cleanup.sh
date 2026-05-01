#!/bin/bash

echo "Cleaning Docker..."
sudo docker image prune  -f
sudo docker builder prune -f

echo "Cleaning temp files..."
sudo rm -rf /tmp/*

echo "Cleanup completed"
