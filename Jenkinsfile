pipeline {
    agent any

    environment {
        BACKEND_IMAGE = "udaykiranchilumula/aws-backend"
        FRONTEND_IMAGE = "udaykiranchilumula/aws-frontend"
    }

    stages {
        stage('Checkout') {
            steps {
                git branch: 'main', url: 'https://github.com/UdayKiranChilumula/DevOps-UseCase.git'
            }
        }

        stage('Build Backend Image') {
            steps {
                dir('backend') {
                    sh "docker build -t ${BACKEND_IMAGE}:latest ."
                }
            }
        }

        stage('Build Frontend Image') {
            steps {
                dir('frontend') {
                    sh "docker build -t ${FRONTEND_IMAGE}:latest ."
                }
            }
        }

        stage('Push Images') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'docker-hub-credentials', usernameVariable: 'DOCKERHUB_USERNAME', passwordVariable: 'DOCKERHUB_PASSWORD')]) {
                    sh """
                    echo "${DOCKERHUB_PASSWORD}" | docker login -u "${DOCKERHUB_USERNAME}" --password-stdin
                    docker push ${BACKEND_IMAGE}:latest
                    docker push ${FRONTEND_IMAGE}:latest
                    """
                }
            }
        }

        stage('Create Kubernetes Secrets') {
    steps {
        withCredentials([
            usernamePassword(credentialsId: 'postgres-credentials', usernameVariable: 'PG_USER', passwordVariable: 'PG_PASSWORD'),
            string(credentialsId: 'postgres-db', variable: 'PG_DB'),
            [$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'aws-credentials']
        ]) {
            sh """
            kubectl delete secret postgres-secret --ignore-not-found
            kubectl create secret generic postgres-secret \
              --from-literal=POSTGRES_USER=${PG_USER} \
              --from-literal=POSTGRES_PASSWORD=${PG_PASSWORD} \
              --from-literal=POSTGRES_DB=${PG_DB}

            kubectl delete secret aws-credentials --ignore-not-found
            kubectl create secret generic aws-credentials \
              --from-literal=AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID} \
              --from-literal=AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
            """
        }
    }
}



        stage('Deploy to Kubernetes') {
            steps {
                sh """
                kubectl apply -f k8s/postgres/
                kubectl apply -f k8s/
                kubectl rollout restart deployment aws-backend
                kubectl rollout restart deployment aws-frontend
                """
            }
        }
    }

    post {
        always {
            echo "Cleaning up cloned repo directory..."
            deleteDir()
        }
    }
}
